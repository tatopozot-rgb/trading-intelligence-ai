// Independent cross-review acceptance tests; no server, browser or network.
// AGENT_CITY_REVIEW_SOURCE points to the directory containing lib/model.mjs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

if (!process.env.AGENT_CITY_REVIEW_SOURCE) throw new Error('Set AGENT_CITY_REVIEW_SOURCE to the pinned source directory');
const { deriveCity } = await import(pathToFileURL(resolve(process.env.AGENT_CITY_REVIEW_SOURCE, 'lib/model.mjs')).href);
const now = new Date('2026-10-06T12:00:00Z');
const snapshot = () => ({ generated_at: '2026-10-06T11:59:00Z', sync: { ok: true },
  agents: [{ key: 'gpt', state: 'NOT_SYNCED', heartbeat: {} }] });
const gpt = city => city.agents.find(a => a.key === 'gpt');

test('future snapshot cannot prove current synchronization', () => {
  const city = deriveCity({ snapshot: { ...snapshot(), generated_at: '2026-10-07T12:00:00Z' }, events: [], now });
  assert.equal(city.syncOk, false);
});

test('future event cannot make a real agent WORKING or create a current pulse', () => {
  const city = deriveCity({ snapshot: snapshot(), events: [{ type: 'TASK_STARTED', subject: 'GPT Work', observed_at: '2026-10-07T12:00:00Z' }], now });
  assert.notEqual(gpt(city).state, 'WORKING');
  assert.equal(city.buildings.find(b => b.id === 'gpt_ops').pulses.length, 0);
});

test('WORKING text in a snapshot is not a qualifying observed work event', () => {
  const city = deriveCity({ snapshot: { ...snapshot(), agents: [{ key: 'gpt', state: 'WORKING', heartbeat: {} }] }, events: [], now });
  assert.notEqual(gpt(city).state, 'WORKING');
});

test('a real recent task-start event still produces WORKING', () => {
  const city = deriveCity({ snapshot: snapshot(), events: [{ type: 'TASK_STARTED', subject: 'GPT Work', observed_at: '2026-10-06T11:59:00Z' }], now });
  assert.equal(gpt(city).state, 'WORKING');
});
