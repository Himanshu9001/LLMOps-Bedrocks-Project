import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate  = new Rate('error_rate');
const ragLatency = new Trend('rag_latency_ms');

export const options = {
  stages: [
    { duration: '30s', target: 3  },
    { duration: '60s', target: 5  },
    { duration: '30s', target: 0  },
  ],
  thresholds: {
    http_req_duration: ['p(95)<15000'],
    error_rate:        ['rate<0.2'],
  },
};

const ALB = 'k8s-llmops-fastapii-7cc3c8b514-1333502527.us-east-1.elb.amazonaws.com';

export default function () {
  const health = http.get(`http://${ALB}/health`);
  check(health, { 'health 200': r => r.status === 200 });

  const payload = JSON.stringify({
    query: 'what are the key features?',
    tenant_id: 'tenant_test'
  });

  const response = http.post(`http://${ALB}/query`, payload, {
    headers: { 'Content-Type': 'application/json' },
    timeout: '20s'
  });

  // Safe JSON parse — handle ALB error pages
  let body = {};
  try { body = JSON.parse(response.body); } catch (_) {}

  const success = check(response, {
    'status 200':   r => r.status === 200,
    'has answer':   () => body.answer !== undefined,
    'has trace_id': () => body.trace_id !== undefined,
  });

  ragLatency.add(response.timings.duration);
  errorRate.add(!success);
  sleep(2);
}

export function handleSummary(data) {
  return {
    stdout: `
=== Load Test Summary ===
Total requests: ${data.metrics.http_reqs.values.count}
Error rate:     ${(data.metrics.error_rate?.values?.rate * 100 || 0).toFixed(2)}%
Median latency: ${data.metrics.http_req_duration.values.med.toFixed(0)}ms
P95 latency:    ${data.metrics.http_req_duration.values['p(95)'].toFixed(0)}ms
P99 latency:    ${data.metrics.http_req_duration.values['p(99)'].toFixed(0)}ms
========================
    `
  };
}
