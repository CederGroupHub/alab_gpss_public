import axios from 'axios';
import * as mockApi from './mockApi';

// Use mock API if the environment variable is set
const useMockApi = process.env.REACT_APP_USE_MOCK_API === 'true'; // Temporarily force mock API

// XRD Sample Holder API
export const getXRDSampleHolderSlots = async () => {
  if (useMockApi) return mockApi.getXRDSampleHolderSlots();
  const response = await axios.get('/api/xrd-sample-holder/');
  return response.data;
};

export const getXRDSampleHolderSlot = async (slot) => {
  if (useMockApi) return mockApi.getXRDSampleHolderSlot(slot);
  const response = await axios.get(`/api/xrd-sample-holder/${slot}/`);
  return response.data;
};

export const markXRDSampleHolderAsClean = async (slot) => {
  if (useMockApi) return mockApi.markXRDSampleHolderAsClean(slot);
  const response = await axios.post(`/api/xrd-sample-holder/${slot}/mark-as-clean/`);
  return response.data;
};

export const disableXRDSampleHolderSlot = async (slot) => {
  if (useMockApi) return mockApi.disableXRDSampleHolderSlot(slot);
  const response = await axios.post(`/api/xrd-sample-holder/${slot}/disable/`);
  return response.data;
};

export const enableXRDSampleHolderSlot = async (slot) => {
  if (useMockApi) return mockApi.enableXRDSampleHolderSlot(slot);
  const response = await axios.post(`/api/xrd-sample-holder/${slot}/enable/`);
  return response.data;
};

export const cleanXRDSampleHolderRow = async (row) => {
  if (useMockApi) return mockApi.cleanXRDSampleHolderRow(row);
  const response = await axios.post(`/api/xrd-sample-holder/row/${row}/clean/`);
  return response.data;
};

export const disableXRDSampleHolderRow = async (row) => {
  if (useMockApi) return mockApi.disableXRDSampleHolderRow(row);
  const response = await axios.post(`/api/xrd-sample-holder/row/${row}/disable/`);
  return response.data;
};

export const enableXRDSampleHolderRow = async (row) => {
  if (useMockApi) return mockApi.enableXRDSampleHolderRow(row);
  const response = await axios.post(`/api/xrd-sample-holder/row/${row}/enable/`);
  return response.data;
};

export const runXRDMeasurement = async (row) => {
  if (useMockApi) return mockApi.runXRDMeasurement(row);
  const response = await axios.post(`/api/xrd-sample-holder/row/${row}/run-measurement/`);
  return response.data;
};

export const getXRDMeasurementProgress = async () => {
  if (useMockApi) return mockApi.getXRDMeasurementProgress();
  const response = await axios.get('/api/xrd-sample-holder/measurement-progress/');
  return response.data;
};

// Dosing Head API
export const getDosingHeads = async () => {
  if (useMockApi) return mockApi.getDosingHeads();
  const response = await axios.get('/api/dosing-head/');
  return response.data;
};

export const getDosingHead = async (slot) => {
  if (useMockApi) return mockApi.getDosingHead(slot);
  const response = await axios.get(`/api/dosing-head/${slot}/`);
  return response.data;
};

export const addDosingHead = async (slot, chemical) => {
  if (useMockApi) return mockApi.addDosingHead(slot, chemical);
  const response = await axios.post(`/api/dosing-head/${slot}/add`, { chemical });
  return response.data;
};

export const clearDosingHeadError = async (slot) => {
  if (useMockApi) return mockApi.clearDosingHeadError(slot);
  const response = await axios.post(`/api/dosing-head/${slot}/clear-error/`);
  return response.data;
};

export const unloadDosingHead = async (slot) => {
  if (useMockApi) return mockApi.unloadDosingHead(slot);
  const response = await axios.post(`/api/dosing-head/${slot}/unload/`);
  return response.data;
};

// Consumable Rack API
export const getConsumableRackSlots = async () => {
  if (useMockApi) return mockApi.getConsumableRackSlots();
  const response = await axios.get('/api/consumable-rack/');
  return response.data;
};

export const getConsumableRackSlot = async (level, row) => {
  if (useMockApi) return mockApi.getConsumableRackSlot(level, row);
  const response = await axios.get(`/api/consumable-rack/${level}/${row}/`);
  return response.data;
};

export const cleanConsumableRackSlot = async (level, row) => {
  if (useMockApi) return mockApi.cleanConsumableRackSlot(level, row);
  const response = await axios.post(`/api/consumable-rack/${level}/${row}/clean/`);
  return response.data;
};

export const cleanConsumableRackLevel = async (level) => {
  if (useMockApi) return mockApi.mockCleanConsumableRackLevel(level);
  const response = await axios.post(`/api/consumable-rack/level/${level}/clean/`);
  return response.data;
};

// Ionic Conductivity API
export const startIonicConductivityMeasurement = async (measurementData) => {
  if (useMockApi) return mockApi.startIonicConductivityMeasurement(measurementData);
  const response = await axios.post('/api/ionic-conductivity/measure/', measurementData);
  return response.data;
};

export const getMeasurementStatus = async () => {
  if (useMockApi) return mockApi.getMeasurementStatus();
  const response = await axios.get('/api/ionic-conductivity/status/');
  return response.data;
};

export const clearMeasurement = async () => {
  if (useMockApi) return mockApi.clearMeasurement();
  const response = await axios.delete('/api/ionic-conductivity/measurement/');
  return response.data;
};

export const getSampleMeasurements = async (sampleId) => {
  if (useMockApi) return mockApi.getSampleMeasurements(sampleId);
  const response = await axios.get(`/api/ionic-conductivity/measurements/${sampleId}/`);
  return response.data;
};

export const getIonicConductivityPlotData = async (sampleId, measurementId = null) => {
  if (useMockApi) return mockApi.getIonicConductivityPlotData(sampleId, measurementId);
  
  // If measurementId is provided, use the specific measurement endpoint
  if (measurementId) {
    const response = await axios.get(`/api/ionic-conductivity/plot/ionic/${sampleId}/${measurementId}/`);
    return response.data;
  }
  
  // Otherwise, use the legacy endpoint that returns the latest measurement
  const response = await axios.get(`/api/ionic-conductivity/plot/ionic/${sampleId}/`);
  return response.data;
};

export const getElectronicConductivityPlotData = async (sampleId, measurementId = null) => {
  if (useMockApi) return mockApi.getElectronicConductivityPlotData(sampleId, measurementId);
  
  // If measurementId is provided, use the specific measurement endpoint
  if (measurementId) {
    const response = await axios.get(`/api/ionic-conductivity/plot/electronic/${sampleId}/${measurementId}/`);
    return response.data;
  }
  
  // Otherwise, use the legacy endpoint that returns the latest measurement
  const response = await axios.get(`/api/ionic-conductivity/plot/electronic/${sampleId}/`);
  return response.data;
};

export const getDefaultMeasurementParameters = async () => {
  if (useMockApi) return mockApi.getDefaultMeasurementParameters();
  const response = await axios.get('/api/ionic-conductivity/defaults/');
  return response.data;
};

export const updateSampleHeight = async (sampleHeight) => {
  if (useMockApi) return mockApi.updateSampleHeight(sampleHeight);
  const response = await axios.patch('/api/ionic-conductivity/sample-height/', { sample_height: sampleHeight });
  return response.data;
};

export const loadSample = async (sampleId, ionicMeasurementId = null, electronicMeasurementId = null) => {
  if (useMockApi) return mockApi.loadSample(sampleId, ionicMeasurementId, electronicMeasurementId);
  
  const requestData = { sample_id: sampleId };
  if (ionicMeasurementId) {
    requestData.ionic_measurement_id = ionicMeasurementId;
  }
  if (electronicMeasurementId) {
    requestData.electronic_measurement_id = electronicMeasurementId;
  }
  
  const response = await axios.post('/api/ionic-conductivity/load-sample/', requestData);
  return response.data;
};