import {request, saveFile} from '../api/http.js';
import {session} from './session.js';

const call = (path, body) => request(path, {token:session.token, body});
export const workspace = {
  spec: null,
  datasets: [],
  runs: [],
  experiments: [],
  async init() { this.spec = await request('/spec'); },
  async refresh() {
    const [datasets, runs, experiments] = await Promise.all([
      call('/datasets'), call('/runs'), call('/experiments')]);
    this.datasets = datasets; this.runs = runs; this.experiments = experiments;
  },
  getDataset: (id, offset = 0) => call(`/datasets/${id}?offset=${offset}`),
  getRun: id => call(`/runs/${id}`),
  upload: data => call('/datasets', data),
  start: data => call('/runs', data),
  review: (id, data) => call(`/runs/${id}/review`, data),
  audit: () => call('/audit'),
  schedules: () => call('/schedules'),
  deliveries: () => call('/deliveries'),
  schedule: data => call('/schedules', data),
  disable: id => call(`/schedules/${id}/disable`, {}),
  download: (path, filename) => saveFile(path, session.token, filename),
  listExperiments: () => call('/experiments'),
  getExperiment: id => call(`/experiments/${id}`),
  registerExperiment: data => call('/experiments', data),
  uploadRecon: (id, data) => call(`/experiments/${id}/reconcile`, data),
  experimentRisk: id => call(`/experiments/${id}/risk`),
  experimentConclusions: id => call(`/experiments/${id}/conclusions`),
};
