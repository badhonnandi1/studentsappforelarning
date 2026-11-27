// k6 load test for OTP verify and refresh (05 §F test plan). Not run in CI, and not run for
// Build 1: no capacity figure is claimed until this has been run against staging.
//
//   k6 run -e BASE_URL=https://api.staging.example -e OTP_CODE=123456 tests/load/auth.js
//
// Target: 200 req/s in total (100 verify + 100 refresh), p95 < 150 ms. The SMS send is
// tagged separately and excluded from the threshold.
//
// Preconditions (see BUILD_01_REPORT.md, "Load test"):
// - Phones come from the reserved block +8801700000000..+8801700009999. Verify needs a known
//   code, and Build 1 accepts a fixed code only in local and test, so the target environment
//   must be a load-test deployment that allows it.
// - Raise the auth tiers for the run through runtime config `ratelimit.overrides`, or the
//   per-IP limits answer 429 long before 200 req/s.
// - If CAPTCHA is required, pass a load-test token with -e CHALLENGE_TOKEN=...
import http from "k6/http";
import { check } from "k6";

const BASE = __ENV.BASE_URL || "http://127.0.0.1:8000";
const CODE = __ENV.OTP_CODE || "123456";
const RATE = Number(__ENV.RATE || 100); // per scenario, per second
const JSON_HEADERS = { headers: { "Content-Type": "application/json" } };

export const options = {
  scenarios: {
    otp_verify: {
      executor: "constant-arrival-rate", exec: "otpVerify", rate: RATE, timeUnit: "1s",
      duration: "5m", preAllocatedVUs: 50, maxVUs: 400,
    },
    refresh: {
      executor: "constant-arrival-rate", exec: "refresh", rate: RATE, timeUnit: "1s",
      duration: "5m", preAllocatedVUs: 50, maxVUs: 400,
    },
  },
  thresholds: {
    "http_req_duration{name:otp_verify}": ["p(95)<150"],
    "http_req_duration{name:refresh}": ["p(95)<150"],
    "checks": ["rate>0.99"],
  },
};

function phone() {
  const n = Math.floor(Math.random() * 10000);
  return `+88017000${String(n).padStart(5, "0")}`;
}

function device() {
  return `load-${__VU}-${Math.random().toString(36).slice(2, 12)}`;
}

function signIn(deviceId) {
  const send = http.post(`${BASE}/v1/auth/otp/send`, JSON.stringify({
    phone: phone(), device_id: deviceId, challenge_token: __ENV.CHALLENGE_TOKEN || null,
  }), { ...JSON_HEADERS, tags: { name: "otp_send" } });
  if (!check(send, { "otp sent": (r) => r.status === 202 })) return null;
  const verify = http.post(`${BASE}/v1/auth/otp/verify`, JSON.stringify({
    challenge_id: send.json("challenge_id"), code: CODE,
    device: { device_id: deviceId, platform: "android" },
  }), { ...JSON_HEADERS, tags: { name: "otp_verify" } });
  check(verify, { "otp verified": (r) => r.status === 200 });
  // An unregistered phone gets a pending sign-up instead of tokens; both are a pass.
  return verify.status === 200 ? verify.json("refresh_token") : null;
}

export function otpVerify() {
  signIn(device());
}

const tokens = {}; // per VU: refresh rotates the token, so each VU keeps its latest one

export function refresh() {
  if (!tokens[__VU]) tokens[__VU] = { device: device(), token: null };
  const state = tokens[__VU];
  if (!state.token) {
    state.token = signIn(state.device);
    if (!state.token) return;
  }
  const res = http.post(`${BASE}/v1/auth/refresh`, JSON.stringify({ refresh_token: state.token }), { ...JSON_HEADERS, tags: { name: "refresh" } });
  check(res, { "refreshed": (r) => r.status === 200 });
  state.token = res.status === 200 ? res.json("refresh_token") : null;
}
