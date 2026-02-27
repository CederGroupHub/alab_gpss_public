import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  Typography,
  Grid,
  Button,
  Box,
  TextField,
  Alert,
  Paper,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  InputAdornment,
  LinearProgress,
  Chip,
  Card,
  CardContent,
  CardHeader,
  Container,
  Divider,
  Stack,
  Checkbox,
  Select,
  MenuItem,
  FormControl,
  InputLabel
} from '@mui/material';
import { 
  QrCodeScanner, 
  Close, 
  CheckCircle, 
  Error, 
  Warning, 
  Science,
  Timeline,
  PlayArrow,
  Speed,
  Memory,
  AutoGraph,
  Edit,
  Check,
  Refresh
} from '@mui/icons-material';
import QrScanner from 'qr-scanner';
import Plot from 'react-plotly.js';
import { startIonicConductivityMeasurement, getMeasurementStatus, getSampleMeasurements, getIonicConductivityPlotData, getElectronicConductivityPlotData, getDefaultMeasurementParameters, updateSampleHeight, loadSample } from '../api/api';

// Separate Plot component with error handling - renders only once for static data
const SafePlotComponent = ({ plotData, sampleId }) => {
  const [plotError, setPlotError] = useState(null);
  
  // Memoize the plot to prevent re-renders since data is static
  const memoizedPlot = useMemo(() => {
    if (!plotData || !plotData.data || !Array.isArray(plotData.data) || plotData.data.length === 0) {
      return (
        <Alert severity="warning">
          No plot data available for this measurement.
        </Alert>
      );
    }

    if (plotError) {
      return (
        <Alert severity="error">
          Plot rendering error: {plotError}
        </Alert>
      );
    }

    try {
      return (
        <Box sx={{ width: '100%', height: 400 }}>
          <Plot
            data={plotData.data}
            layout={{
              ...plotData.layout,
              margin: { l: 60, r: 60, t: 80, b: 60 },
              autosize: true
            }}
            config={{
              displayModeBar: true,
              modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
              responsive: true,
              displaylogo: false
            }}
            style={{ width: '100%', height: '100%' }}
            useResizeHandler={true}
            onError={(error) => {
              console.error('Plotly error:', error);
              setPlotError('Plot rendering failed');
            }}
            onInitialized={() => {
              console.log('Plot initialized successfully for sample:', sampleId);
            }}
          />
        </Box>
      );
    } catch (error) {
      console.error('Plot component error:', error);
      return (
        <Alert severity="error">
          Failed to render plot: {error.message}
        </Alert>
      );
    }
  }, [plotData, plotError, sampleId]); // Only re-render if these change

  return memoizedPlot;
};

const IonicConductivityPage = () => {
  const [sampleId, setSampleId] = useState('');
  // PEIS parameter states - will be populated from backend defaults
  const [finalFrequency, setFinalFrequency] = useState('');
  const [initialFrequency, setInitialFrequency] = useState('');
  const [frequencyNumber, setFrequencyNumber] = useState('');
  const [repeat, setRepeat] = useState('');
  const [defaultParams, setDefaultParams] = useState(null);
  // Formatted display values for frequency fields
  const [initialFrequencyDisplay, setInitialFrequencyDisplay] = useState('');
  const [finalFrequencyDisplay, setFinalFrequencyDisplay] = useState('');
  // Electronic conductivity states
  const [includeElectronicConductivity, setIncludeElectronicConductivity] = useState(false);
  const [voltages, setVoltages] = useState('');
  const [durations, setDurations] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [qrScannerOpen, setQrScannerOpen] = useState(false);
  const [qrScanning, setQrScanning] = useState(false);
  const [qrError, setQrError] = useState(null);
  const [sampleIdError, setSampleIdError] = useState('');
  const [currentMeasurement, setCurrentMeasurement] = useState(null);
  const [plotData, setPlotData] = useState(null);
  const [plotLoading, setPlotLoading] = useState(false);
  const [plotError, setPlotError] = useState(null);
  const [electronicPlotData, setElectronicPlotData] = useState(null);
  const [electronicPlotLoading, setElectronicPlotLoading] = useState(false);
  const [electronicPlotError, setElectronicPlotError] = useState(null);
  // Sample height editing states
  const [isEditingHeight, setIsEditingHeight] = useState(false);
  const [editingHeight, setEditingHeight] = useState('');
  // Measurement selection states
  const [sampleMeasurements, setSampleMeasurements] = useState(null);
  const [measurementSelectionOpen, setMeasurementSelectionOpen] = useState(false);
  const [selectedIonicMeasurement, setSelectedIonicMeasurement] = useState('');
  const [selectedElectronicMeasurement, setSelectedElectronicMeasurement] = useState('');
  const videoRef = useRef(null);
  const qrScannerRef = useRef(null);
  const pollIntervalRef = useRef(null);
  const previousMeasurementRef = useRef(null); // Track previous measurement to detect completion
  const loadedSamplesRef = useRef(new Set()); // Track which samples have been loaded

  // ObjectID validation regex (24 hexadecimal characters)
  const objectIdRegex = /^[0-9a-fA-F]{24}$/;

  // Helper functions for number formatting
  const formatNumberWithCommas = (value) => {
    if (!value || value === '') return '';
    // Remove any existing commas and non-numeric characters except decimal point
    const numericValue = value.toString().replace(/[^\d.]/g, '');
    if (numericValue === '') return '';
    
    // Add commas for thousands separation
    const parts = numericValue.split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return parts.join('.');
  };

  const parseFormattedNumber = (formattedValue) => {
    if (!formattedValue || formattedValue === '') return '';
    // Remove commas and return the numeric string
    return formattedValue.replace(/,/g, '');
  };

  // Helper functions for parsing electronic conductivity parameters
  const parseNumberArray = (value) => {
    if (!value || value.trim() === '') return [];
    return value.split(',').map(v => parseFloat(v.trim())).filter(v => !isNaN(v));
  };

  const validateElectronicParams = () => {
    if (!includeElectronicConductivity) return null;
    
    const voltageArray = parseNumberArray(voltages);
    const durationArray = parseNumberArray(durations);
    
    if (voltageArray.length === 0) {
      return 'Voltages cannot be empty when electronic conductivity is enabled';
    }
    
    if (durationArray.length === 0) {
      return 'Durations cannot be empty when electronic conductivity is enabled';
    }
    
    if (voltageArray.length !== durationArray.length) {
      return 'Number of voltages and durations must match';
    }
    
    if (durationArray.some(d => d <= 0)) {
      return 'All durations must be positive';
    }
    
    return null;
  };

  const validateSampleId = (id) => {
    if (!id.trim()) {
      return 'Sample ID is required';
    }
    if (!objectIdRegex.test(id.trim())) {
      return 'Sample ID must be a valid ObjectID (24 hexadecimal characters)';
    }
    return '';
  };

  const handleSampleIdChange = (e) => {
    const value = e.target.value;
    setSampleId(value);
    
    // Real-time validation
    const validationError = validateSampleId(value);
    setSampleIdError(validationError);
  };

  const handleInitialFrequencyChange = (e) => {
    const inputValue = e.target.value;
    const formattedValue = formatNumberWithCommas(inputValue);
    const numericValue = parseFormattedNumber(formattedValue);
    
    setInitialFrequencyDisplay(formattedValue);
    setInitialFrequency(numericValue);
  };

  const handleFinalFrequencyChange = (e) => {
    const inputValue = e.target.value;
    const formattedValue = formatNumberWithCommas(inputValue);
    const numericValue = parseFormattedNumber(formattedValue);
    
    setFinalFrequencyDisplay(formattedValue);
    setFinalFrequency(numericValue);
  };

  const loadDefaultElectronicParams = () => {
    if (defaultParams && defaultParams.electronic_conductivity_params) {
      const electronParams = defaultParams.electronic_conductivity_params;
      setVoltages(electronParams.voltages.join(', '));
      setDurations(electronParams.durations.join(', '));
    } else {
      // Fallback to match DEFAULT_CA_PARAMS from biologic.py
      setVoltages('0.5');
      setDurations('600');
    }
  };

  const handleElectronicConductivityChange = (checked) => {
    setIncludeElectronicConductivity(checked);
    if (checked) {
      // Load default values when checkbox is checked
      loadDefaultElectronicParams();
    } else {
      // Clear values when checkbox is unchecked
      setVoltages('');
      setDurations('');
    }
  };

  const loadPlotData = async (sampleId, ionicMeasurementId = null, electronicMeasurementId = null) => {
    // Create a unique key for this specific measurement combination
    const cacheKey = `${sampleId}_${ionicMeasurementId || 'latest'}_${electronicMeasurementId || 'latest'}`;
    
    // Check if we've already loaded this specific measurement combination
    if (loadedSamplesRef.current.has(cacheKey)) {
      console.log('Plot data already loaded for measurement combination:', cacheKey);
      return;
    }
    
    console.log('Loading ionic plot data for sample:', sampleId, 'measurement:', ionicMeasurementId);
    setPlotLoading(true);
    setPlotError(null);
    setPlotData(null); // Clear existing plot data
    
    try {
      const plotData = await getIonicConductivityPlotData(sampleId, ionicMeasurementId);
      
      // Validate plotData structure before setting it
      if (plotData && 
          plotData.data && 
          Array.isArray(plotData.data) && 
          plotData.layout && 
          typeof plotData.layout === 'object') {
        
        // Ensure each data trace has required properties
        const validatedData = plotData.data.map(trace => ({
          ...trace,
          x: Array.isArray(trace.x) ? trace.x : [],
          y: Array.isArray(trace.y) ? trace.y : [],
          mode: trace.mode || 'markers',
          type: trace.type || 'scatter'
        }));
        
        setPlotData({
          data: validatedData,
          layout: plotData.layout,
          _sampleId: sampleId,
          _measurementId: ionicMeasurementId
        });
        
        console.log('Ionic plot data loaded successfully for sample:', sampleId);
      } else {
        throw new Error('Invalid ionic plot data structure received');
      }
    } catch (error) {
      console.error('Error loading ionic plot data:', error);
      setPlotError(error.response?.data?.detail || error.message || 'Failed to load ionic plot data');
      setPlotData(null);
    } finally {
      setPlotLoading(false);
    }
    
    // Load electronic plot data if available
    await loadElectronicPlotData(sampleId, electronicMeasurementId);
    
    // Mark this measurement combination as loaded
    loadedSamplesRef.current.add(cacheKey);
  };

  const loadElectronicPlotData = async (sampleId, measurementId = null) => {
    console.log('Loading electronic plot data for sample:', sampleId, 'measurement:', measurementId);
    setElectronicPlotLoading(true);
    setElectronicPlotError(null);
    setElectronicPlotData(null);
    
    try {
      const plotData = await getElectronicConductivityPlotData(sampleId, measurementId);
      
      // Validate plotData structure before setting it
      if (plotData && 
          plotData.data && 
          Array.isArray(plotData.data) && 
          plotData.layout && 
          typeof plotData.layout === 'object') {
        
        // Ensure each data trace has required properties
        const validatedData = plotData.data.map(trace => ({
          ...trace,
          x: Array.isArray(trace.x) ? trace.x : [],
          y: Array.isArray(trace.y) ? trace.y : [],
          mode: trace.mode || 'markers',
          type: trace.type || 'scatter'
        }));
        
        setElectronicPlotData({
          data: validatedData,
          layout: plotData.layout,
          _sampleId: sampleId,
          _measurementId: measurementId
        });
        
        console.log('Electronic plot data loaded successfully for sample:', sampleId);
      } else {
        throw new Error('Invalid electronic plot data structure received');
      }
    } catch (error) {
      console.error('Error loading electronic plot data:', error);
      // Don't show error if it's just that the data doesn't exist
      if (error.response?.status === 404) {
        console.log('No electronic conductivity data found for sample:', sampleId);
        setElectronicPlotError(null);
      } else {
        setElectronicPlotError(error.response?.data?.detail || error.message || 'Failed to load electronic plot data');
      }
      setElectronicPlotData(null);
    } finally {
      setElectronicPlotLoading(false);
    }
  };

  const loadDefaultParameters = async () => {
    try {
      console.log('Loading default measurement parameters...');
      const defaultData = await getDefaultMeasurementParameters();
      
      if (defaultData && defaultData.peis_params) {
        setDefaultParams(defaultData); // Store the complete defaultData object
        // Set the form fields with default values
        const initialFreqStr = defaultData.peis_params.initial_frequency.toString();
        const finalFreqStr = defaultData.peis_params.final_frequency.toString();
        
        setFinalFrequency(finalFreqStr);
        setInitialFrequency(initialFreqStr);
        setFrequencyNumber(defaultData.peis_params.frequency_number.toString());
        setRepeat(defaultData.peis_params.repeat.toString());
        
        // Set formatted display values
        setInitialFrequencyDisplay(formatNumberWithCommas(initialFreqStr));
        setFinalFrequencyDisplay(formatNumberWithCommas(finalFreqStr));
        
        console.log('Default parameters loaded:', defaultData);
      }
    } catch (error) {
      console.error('Error loading default parameters:', error);
      // Fallback to hardcoded defaults if API fails
      const fallbackDefaults = {
        peis_params: {
          initial_frequency: 70000000,
          final_frequency: 0.007,
          frequency_number: 6,
          repeat: 0
        },
        electronic_conductivity_params: {
          voltages: [0.5],  // From DEFAULT_CA_PARAMS
          durations: [600]  // From DEFAULT_CA_PARAMS (10 minutes)
        }
      };
      setDefaultParams(fallbackDefaults);
      
      const initialFreqStr = fallbackDefaults.peis_params.initial_frequency.toString();
      const finalFreqStr = fallbackDefaults.peis_params.final_frequency.toString();
      
      setFinalFrequency(finalFreqStr);
      setInitialFrequency(initialFreqStr);
      setFrequencyNumber(fallbackDefaults.peis_params.frequency_number.toString());
      setRepeat(fallbackDefaults.peis_params.repeat.toString());
      
      // Set formatted display values
      setInitialFrequencyDisplay(formatNumberWithCommas(initialFreqStr));
      setFinalFrequencyDisplay(formatNumberWithCommas(finalFreqStr));
    }
  };



  const fetchMeasurementStatus = async () => {
    try {
      const measurement = await getMeasurementStatus();
      
      // Check if we got an empty response (no current measurement)
      if (!measurement || Object.keys(measurement).length === 0) {
        previousMeasurementRef.current = null;
        setCurrentMeasurement(null);
        setPlotData(null);
        setElectronicPlotData(null);
        setElectronicPlotError(null);
        // Clear loaded samples when no measurement
        loadedSamplesRef.current.clear();
        return;
      }
      
      const previousMeasurement = previousMeasurementRef.current;
      
      // Check if measurement just completed
      if (measurement.status === 'completed' && 
          (!previousMeasurement || previousMeasurement.status !== 'completed')) {
        console.log('Measurement just completed, loading plot data for:', measurement.sample_id);
        // Remove from cache and load fresh plot data
        const cacheKey = `${measurement.sample_id}_latest_latest`;
        loadedSamplesRef.current.delete(cacheKey);
        
        // Use the measurement IDs from the completed measurement if available
        const ionicMeasurementId = measurement.latest_ionic_measurement_id || null;
        const electronicMeasurementId = measurement.latest_electronic_measurement_id || null;
        
        await loadPlotData(measurement.sample_id, ionicMeasurementId, electronicMeasurementId);
      }
      
      // Update refs
      previousMeasurementRef.current = measurement;
      setCurrentMeasurement(measurement);
    } catch (err) {
      console.error('Failed to fetch measurement status:', err);
      // Any other error (network, server error, etc.) should be logged
      // but we don't need to clear the measurement state unless it's specifically a "no measurement" case
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validation
    const sampleIdValidationError = validateSampleId(sampleId);
    if (sampleIdValidationError) {
      setError(sampleIdValidationError);
      setSampleIdError(sampleIdValidationError);
      return;
    }

    // Validate PEIS parameters
    if (!initialFrequency || isNaN(initialFrequency) || parseFloat(initialFrequency) <= 0) {
      setError('Initial frequency must be a positive number');
      return;
    }
    
    if (!finalFrequency || isNaN(finalFrequency) || parseFloat(finalFrequency) <= 0) {
      setError('Final frequency must be a positive number');
      return;
    }
    
    if (!frequencyNumber || isNaN(frequencyNumber) || parseInt(frequencyNumber) <= 0) {
      setError('Frequency number must be a positive integer');
      return;
    }
    
    if (isNaN(repeat) || parseInt(repeat) < 0) {
      setError('Repeat count must be a non-negative integer');
      return;
    }

    // Validate electronic conductivity parameters if enabled
    const electronicValidationError = validateElectronicParams();
    if (electronicValidationError) {
      setError(electronicValidationError);
      return;
    }

    // Proceed with measurement directly (no overwrite checking)
    setLoading(true);
    setError(null);
    setSampleIdError('');

    const measurementData = {
      sample_id: sampleId.trim(),
      peis_params: {
        initial_frequency: parseFloat(initialFrequency),
        final_frequency: parseFloat(finalFrequency),
        frequency_number: parseInt(frequencyNumber),
        repeat: parseInt(repeat)
      },
      include_electronic_conductivity: includeElectronicConductivity
    };

    if (includeElectronicConductivity) {
      measurementData.electronic_conductivity_params = {
        voltages: parseNumberArray(voltages),
        durations: parseNumberArray(durations)
      };
    }

    await proceedWithMeasurement(measurementData);
  };

  const proceedWithMeasurement = async (measurementData) => {
    try {
      await startIonicConductivityMeasurement(measurementData);
      
      // Reset form
      setSampleId('');
      // Reset PEIS parameters to defaults
      if (defaultParams && defaultParams.peis_params) {
        const initialFreqStr = defaultParams.peis_params.initial_frequency.toString();
        const finalFreqStr = defaultParams.peis_params.final_frequency.toString();
        
        setFinalFrequency(finalFreqStr);
        setInitialFrequency(initialFreqStr);
        setFrequencyNumber(defaultParams.peis_params.frequency_number.toString());
        setRepeat(defaultParams.peis_params.repeat.toString());
        
        // Reset formatted display values
        setInitialFrequencyDisplay(formatNumberWithCommas(initialFreqStr));
        setFinalFrequencyDisplay(formatNumberWithCommas(finalFreqStr));
      }
      
      // Reset electronic conductivity parameters
      setIncludeElectronicConductivity(false);
      setVoltages('');
      setDurations('');
      
      // Fetch the new measurement status
      fetchMeasurementStatus();
      
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start measurement');
    } finally {
      setLoading(false);
    }
  };



  const getStatusColor = (status) => {
    switch (status) {
      case 'completed':
        return 'success';
      case 'running':
        return 'info';
      case 'queued':
        return 'warning';
      case 'failed':
        return 'error';
      default:
        return 'default';
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString();
  };

  const handleOpenQrScanner = async () => {
    try {
      setQrError(null);
      setQrScannerOpen(true);
      setQrScanning(true);
      
      // Wait for the dialog to be fully rendered
      setTimeout(async () => {
        if (videoRef.current) {
          try {
            // Try the direct approach first
            qrScannerRef.current = new QrScanner(
              videoRef.current,
              (result) => {
                console.log('QR Code detected:', result);
                const scannedId = result.data;
                
                // Validate the scanned data before acting on it
                if (!scannedId || scannedId.trim().length === 0) {
                  console.log('Empty QR code detected, ignoring');
                  return; // Don't close scanner for empty codes
                }

                console.log('Valid QR code detected:', scannedId);
                setSampleId(scannedId.trim());
                
                // Validate the scanned QR code
                const validationError = validateSampleId(scannedId.trim());
                setSampleIdError(validationError);
                
                handleCloseQrScanner();
              },
              {
                returnDetailedScanResult: true,
                highlightScanRegion: false,
                highlightCodeOutline: true,
                maxScansPerSecond: 25,
                preferredCamera: 'environment',
                calculateScanRegion: (video) => {
                  const videoWidth = video.videoWidth;
                  const videoHeight = video.videoHeight;
                  console.log('QR Scanner video dimensions:', { videoWidth, videoHeight });
                  return {
                    x: 0,
                    y: 0,
                    width: videoWidth,
                    height: videoHeight
                  };
                }
              }
            );
            
            console.log('Starting QR scanner...');
            await qrScannerRef.current.start();
            console.log('QR scanner started successfully');
            setQrScanning(false);
          } catch (err) {
            console.error('QR Scanner start error:', err);
            setQrError('Failed to access camera. Please check camera permissions.');
            setQrScanning(false);
          }
        }
      }, 100);
    } catch (err) {
      console.error('QR Scanner setup error:', err);
      setQrError('Failed to initialize QR scanner.');
      setQrScanning(false);
    }
  };

  const handleCloseQrScanner = () => {
    if (qrScannerRef.current) {
      qrScannerRef.current.stop();
      qrScannerRef.current.destroy();
      qrScannerRef.current = null;
    }
    setQrScannerOpen(false);
    setQrScanning(false);
    setQrError(null);
  };

  const handleEditHeight = () => {
    if (currentMeasurement && currentMeasurement.sample_height) {
      setEditingHeight(currentMeasurement.sample_height.toString());
    } else {
      setEditingHeight('');
    }
    setIsEditingHeight(true);
  };

  const handleUpdateHeight = async () => {
    if (!editingHeight || isNaN(editingHeight) || parseFloat(editingHeight) <= 0) {
      alert('Please enter a valid positive number for sample height');
      return;
    }

    try {
      setLoading(true);
      const result = await updateSampleHeight(parseFloat(editingHeight));
      console.log('Sample height updated successfully:', result);
      setIsEditingHeight(false);
      setEditingHeight('');
      // Refresh measurement status
      await fetchMeasurementStatus();
      // Show success message
      setError(null);
    } catch (error) {
      console.error('Error updating sample height:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to update sample height';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleCancelEdit = () => {
    setIsEditingHeight(false);
    setEditingHeight('');
  };

  const handleLoadSample = async () => {
    // Validate sample ID first
    const validationError = validateSampleId(sampleId);
    if (validationError) {
      setError(validationError);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      
      // Get all measurements for this sample
      const measurements = await getSampleMeasurements(sampleId.trim());
      
      // Check if there are no measurements
      if (!measurements.ionic_conductivity_measurements?.length && 
          !measurements.electronic_conductivity_measurements?.length) {
        setError('No conductivity measurements found for this sample');
        setLoading(false);
        return;
      }
      
      // Check if there are multiple measurements - show selection dialog
      const hasMultipleIonic = measurements.ionic_conductivity_measurements?.length > 1;
      const hasMultipleElectronic = measurements.electronic_conductivity_measurements?.length > 1;
      
      if (hasMultipleIonic || hasMultipleElectronic) {
        // Show measurement selection dialog
        setSampleMeasurements(measurements);
        
        // Set default selections to latest measurements
        if (measurements.ionic_conductivity_measurements?.length > 0) {
          setSelectedIonicMeasurement(measurements.ionic_conductivity_measurements[measurements.ionic_conductivity_measurements.length - 1].measurement_id);
        }
        if (measurements.electronic_conductivity_measurements?.length > 0) {
          setSelectedElectronicMeasurement(measurements.electronic_conductivity_measurements[measurements.electronic_conductivity_measurements.length - 1].measurement_id);
        }
        
        setMeasurementSelectionOpen(true);
        setLoading(false);
        return;
      }
      
      // Single measurement or no multiple measurements - load directly
      const ionicMeasurementId = measurements.ionic_conductivity_measurements?.[0]?.measurement_id || null;
      const electronicMeasurementId = measurements.electronic_conductivity_measurements?.[0]?.measurement_id || null;
      
      await loadSampleWithMeasurements(sampleId.trim(), ionicMeasurementId, electronicMeasurementId);
      
    } catch (error) {
      console.error('Error loading sample:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to load sample measurement';
      setError(errorMessage);
      setLoading(false);
    }
  };

  const loadSampleWithMeasurements = async (sampleId, ionicMeasurementId, electronicMeasurementId) => {
    try {
      setLoading(true);
      setError(null);
      
      // Load the specific measurement
      const loadedMeasurement = await loadSample(sampleId, ionicMeasurementId, electronicMeasurementId);
      
      // Update current measurement state
      setCurrentMeasurement(loadedMeasurement);
      
      // Update form fields with loaded measurement data
      if (loadedMeasurement.peis_params) {
        const params = loadedMeasurement.peis_params;
        const initialFreqStr = params.initial_frequency.toString();
        const finalFreqStr = params.final_frequency.toString();
        
        setInitialFrequency(initialFreqStr);
        setFinalFrequency(finalFreqStr);
        setFrequencyNumber(params.frequency_number.toString());
        setRepeat(params.repeat.toString());
        
        // Set formatted display values
        setInitialFrequencyDisplay(formatNumberWithCommas(initialFreqStr));
        setFinalFrequencyDisplay(formatNumberWithCommas(finalFreqStr));
      }
      
      // Update electronic conductivity fields if available
      if (loadedMeasurement.include_electronic_conductivity && loadedMeasurement.electronic_conductivity_params) {
        setIncludeElectronicConductivity(true);
        const electronicsParams = loadedMeasurement.electronic_conductivity_params;
        setVoltages(electronicsParams.voltages.join(', '));
        setDurations(electronicsParams.durations.join(', '));
      } else {
        setIncludeElectronicConductivity(false);
        setVoltages('');
        setDurations('');
      }
      
      // Clear any existing plot data to force reload
      setPlotData(null);
      setPlotError(null);
      setElectronicPlotData(null);
      setElectronicPlotError(null);
      loadedSamplesRef.current.clear();
      
      // Load plot data for the specific measurements
      await loadPlotData(sampleId, ionicMeasurementId, electronicMeasurementId);
      
    } catch (error) {
      console.error('Error loading sample with measurements:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to load sample measurement';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleMeasurementSelectionConfirm = async () => {
    setMeasurementSelectionOpen(false);
    
    const ionicId = selectedIonicMeasurement || null;
    const electronicId = selectedElectronicMeasurement || null;
    
    await loadSampleWithMeasurements(sampleId.trim(), ionicId, electronicId);
    
    // Clear selection state
    setSampleMeasurements(null);
    setSelectedIonicMeasurement('');
    setSelectedElectronicMeasurement('');
  };

  const handleMeasurementSelectionCancel = () => {
    setMeasurementSelectionOpen(false);
    setSampleMeasurements(null);
    setSelectedIonicMeasurement('');
    setSelectedElectronicMeasurement('');
    setLoading(false);
  };

  // Cleanup QR scanner on unmount and setup measurement polling
  useEffect(() => {
    // Fetch measurement status on mount
    const initializeData = async () => {
      await Promise.all([
        loadDefaultParameters(),
        fetchMeasurementStatus()
      ]);
    };
    initializeData();
    
    // Setup polling for measurement updates (every 2 seconds)
    pollIntervalRef.current = setInterval(() => {
      fetchMeasurementStatus();
    }, 2000);
    
    return () => {
      if (qrScannerRef.current) {
        qrScannerRef.current.stop();
        qrScannerRef.current.destroy();
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  // Handle plot data fetching when measurement completes or page loads with completed measurement
  useEffect(() => {
    if (currentMeasurement && currentMeasurement.status === 'completed') {
      // Determine measurement IDs to use
      const ionicMeasurementId = currentMeasurement.loaded_ionic_measurement_id || 
                                currentMeasurement.latest_ionic_measurement_id || null;
      const electronicMeasurementId = currentMeasurement.loaded_electronic_measurement_id || 
                                    currentMeasurement.latest_electronic_measurement_id || null;
      
      const cacheKey = `${currentMeasurement.sample_id}_${ionicMeasurementId || 'latest'}_${electronicMeasurementId || 'latest'}`;
      
      console.log('Plot useEffect triggered:', {
        sampleId: currentMeasurement.sample_id,
        status: currentMeasurement.status,
        ionicMeasurementId,
        electronicMeasurementId,
        hasLoaded: loadedSamplesRef.current.has(cacheKey)
      });
      
      // Only load if we haven't loaded this measurement combination yet
      if (!loadedSamplesRef.current.has(cacheKey)) {
        console.log('Loading plot data on initial load for completed measurement:', currentMeasurement.sample_id);
        loadPlotData(currentMeasurement.sample_id, ionicMeasurementId, electronicMeasurementId);
      }
    } else if (!currentMeasurement || currentMeasurement.status !== 'completed') {
      // Clear plot data if no measurement or measurement is not completed
      setPlotData(null);
      setPlotError(null);
      setElectronicPlotData(null);
      setElectronicPlotError(null);
    }
  }, [currentMeasurement?.sample_id, currentMeasurement?.status, currentMeasurement?.loaded_ionic_measurement_id, currentMeasurement?.loaded_electronic_measurement_id]);

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>

      {error && (
        <Alert 
          severity="error" 
          sx={{ mb: 3 }} 
          onClose={() => setError(null)}
        >
          {error}
        </Alert>
      )}

      {/* Two Column Layout */}
      <Grid container spacing={4}>
        {/* Left Column - Start New Measurement Form */}
        <Grid item xs={12} lg={6}>
          <Card sx={{ 
            height: 'fit-content'
          }}>
            <CardHeader 
              title="Start New Measurement"
              subheader="Configure and initiate ionic conductivity analysis"
              avatar={<PlayArrow color="primary" />}
            />
            <CardContent>
              <Box component="form" onSubmit={handleSubmit}>
                <Grid container spacing={3}>
                  <Grid item xs={12}>
                    <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                      <TextField
                        fullWidth
                        label="Sample ID"
                        value={sampleId}
                        onChange={handleSampleIdChange}
                        placeholder="Enter sample identifier or scan QR code"
                        disabled={loading}
                        required
                        error={!!sampleIdError}
                        helperText={sampleIdError || 'ObjectID format: 24 hexadecimal characters (0-9, a-f, A-F)'}
                        InputProps={{
                          endAdornment: (
                            <InputAdornment position="end">
                              <IconButton
                                onClick={handleOpenQrScanner}
                                disabled={loading}
                                title="Scan QR Code"
                                color="primary"
                              >
                                <QrCodeScanner />
                              </IconButton>
                            </InputAdornment>
                          ),
                        }}
                      />
                      <Button
                        variant="outlined"
                        onClick={handleLoadSample}
                        disabled={loading || !sampleId.trim() || !!sampleIdError}
                        startIcon={<Timeline />}
                        size="medium"
                        sx={{ minWidth: 140, height: 56 }} // Match text field height
                      >
                        Load Sample
                      </Button>
                    </Box>
                  </Grid>

                  
                  {/* PEIS Parameters Section */}
                  <Grid item xs={12}>
                    <Divider sx={{ my: 2 }}>
                      <Chip label="PEIS Measurement Parameters" size="small" />
                    </Divider>
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="Initial Frequency (Hz)"
                      type="text"
                      value={initialFrequencyDisplay}
                      onChange={handleInitialFrequencyChange}
                      placeholder="Enter initial frequency"
                      disabled={loading}
                      required
                      helperText="Start frequency for measurement (default: 70,000,000 Hz)"
                    />
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="Final Frequency (Hz)"
                      type="text"
                      value={finalFrequencyDisplay}
                      onChange={handleFinalFrequencyChange}
                      placeholder="Enter final frequency"
                      disabled={loading}
                      required
                      helperText="End frequency for measurement (default: 0.007 Hz)"
                    />
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="Frequency Number"
                      type="number"
                      value={frequencyNumber}
                      onChange={(e) => setFrequencyNumber(e.target.value)}
                      placeholder="Enter number of frequencies"
                      disabled={loading}
                      required
                      inputProps={{
                        min: "1",
                        step: "1"
                      }}
                      helperText="Number of frequency points per decade"
                    />
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="Repeat"
                      type="number"
                      value={repeat}
                      onChange={(e) => setRepeat(e.target.value)}
                      placeholder="Enter repeat count"
                      disabled={loading}
                      required
                      inputProps={{
                        min: "0",
                        step: "1"
                      }}
                      helperText="Number of measurement repetitions"
                    />
                  </Grid>

                  {/* Electronic Conductivity Section */}
                  <Grid item xs={12}>
                    <Divider sx={{ my: 2 }}>
                      <Chip label="Electronic Conductivity (Optional)" size="small" />
                    </Divider>
                  </Grid>

                  <Grid item xs={12}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Checkbox
                        checked={includeElectronicConductivity}
                        onChange={(e) => handleElectronicConductivityChange(e.target.checked)}
                        disabled={loading}
                        color="primary"
                      />
                      <Typography variant="body1">
                        Include Electronic Conductivity Measurement
                      </Typography>
                      <AutoGraph color="primary" sx={{ ml: 1 }} />
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ ml: 4 }}>
                      Enable this to perform additional electronic conductivity measurements
                    </Typography>
                  </Grid>

                  {includeElectronicConductivity && (
                    <>
                      <Grid item xs={12} sm={6}>
                        <TextField
                          fullWidth
                          label="Voltages (V)"
                          type="text"
                          value={voltages}
                          onChange={(e) => setVoltages(e.target.value)}
                          placeholder="e.g., 0.5"
                          disabled={loading}
                          required={includeElectronicConductivity}
                          helperText="Comma-separated list of voltages to apply (default: 0.5)"
                        />
                      </Grid>
                      
                      <Grid item xs={12} sm={6}>
                        <TextField
                          fullWidth
                          label="Durations (s)"
                          type="text"
                          value={durations}
                          onChange={(e) => setDurations(e.target.value)}
                          placeholder="e.g., 600"
                          disabled={loading}
                          required={includeElectronicConductivity}
                          helperText="Comma-separated list of measurement durations (default: 600 = 10 minutes)"
                        />
                      </Grid>
                    </>
                  )}
                  
                  <Grid item xs={12}>
                    <Button
                      type="submit"
                      variant="contained"
                      size="large"
                      fullWidth
                      disabled={loading || (currentMeasurement && (currentMeasurement.status === 'running' || currentMeasurement.status === 'queued'))}
                      startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <Science />}
                    >
                      {loading ? 'Starting Measurement...' : 
                       (currentMeasurement && (currentMeasurement.status === 'running' || currentMeasurement.status === 'queued')) ? 
                       'Measurement in Progress...' : 
                       includeElectronicConductivity ? 'Start Ionic & Electronic Measurements' : 'Start Ionic Measurement'}
                    </Button>
                  </Grid>
                  
                  {currentMeasurement && (currentMeasurement.status === 'running' || currentMeasurement.status === 'queued') && (
                    <Grid item xs={12}>
                      <Alert severity="info" sx={{ mt: 1 }}>
                        A measurement is currently running. Please wait for it to complete before starting a new one.
                      </Alert>
                    </Grid>
                  )}
                </Grid>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Right Column - Current Measurement Status */}
        <Grid item xs={12} lg={6}>
          {currentMeasurement && (
            <Card sx={{ height: 'fit-content' }}>
              <CardHeader 
                title="Current Measurement"
                subheader={currentMeasurement.include_electronic_conductivity ? 
                  "Ionic & Electronic Conductivity" : "Ionic Conductivity"
                }
                action={
                  <Chip 
                    label={currentMeasurement.status.toUpperCase()} 
                    color={getStatusColor(currentMeasurement.status)}
                  />
                }
              />
                             <CardContent>
                  <Grid container spacing={2}>
                    <Grid item xs={12}>
                      <Typography variant="body2" color="text.secondary">
                        Sample
                      </Typography>
                      <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                        {currentMeasurement.sample_id}
                      </Typography>
                      {currentMeasurement.sample_name && (
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                          {currentMeasurement.sample_name}
                        </Typography>
                      )}
                    </Grid>
                    <Grid item xs={12}>
                      <Typography variant="body2" color="text.secondary">
                        Sample Height
                      </Typography>
                      {isEditingHeight ? (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
                          <TextField
                            size="small"
                            type="number"
                            value={editingHeight}
                            onChange={(e) => setEditingHeight(e.target.value)}
                            placeholder="Enter height in mm"
                            disabled={loading}
                            inputProps={{
                              min: "0.1",
                              step: "0.1"
                            }}
                            sx={{ flexGrow: 1 }}
                          />
                          <IconButton 
                            onClick={handleUpdateHeight} 
                            color="primary" 
                            size="small"
                            disabled={loading || !editingHeight || isNaN(editingHeight) || parseFloat(editingHeight) <= 0}
                          >
                            <Check />
                          </IconButton>
                          <IconButton 
                            onClick={handleCancelEdit} 
                            color="secondary" 
                            size="small"
                            disabled={loading}
                          >
                            <Close />
                          </IconButton>
                        </Box>
                      ) : (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography variant="body1">
                            {currentMeasurement.sample_height ? `${currentMeasurement.sample_height} mm` : 'Not set'}
                          </Typography>
                          <IconButton 
                            onClick={handleEditHeight} 
                            size="small" 
                            color="primary"
                            disabled={loading || currentMeasurement.status === 'running'}
                          >
                            <Edit />
                          </IconButton>
                        </Box>
                      )}
                    </Grid>
                    <Grid item xs={12}>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                        Progress
                      </Typography>
                      <LinearProgress 
                        variant="determinate" 
                        value={currentMeasurement.progress * 100} 
                        sx={{ 
                          mb: 1,
                          '& .MuiLinearProgress-bar': {
                            backgroundColor: currentMeasurement.status === 'completed'
                              ? '#4caf50'
                              : currentMeasurement.status === 'failed' || currentMeasurement.status === 'error'
                                ? '#f44336'
                                : undefined
                          }
                        }}
                      />
                      <Typography variant="body2">
                        {Math.round(currentMeasurement.progress * 100)}% - {currentMeasurement.message}
                      </Typography>
                    </Grid>
                    {/* Display measurement parameters if electronic conductivity is included */}
                    
                    <Grid item xs={12}>
                      <Typography variant="body2" color="text.secondary">
                        Started: {formatDate(currentMeasurement.created_at)}
                      </Typography>
                      {currentMeasurement.completed_at && (
                        <Typography variant="body2" color="text.secondary">
                          Completed: {formatDate(currentMeasurement.completed_at)}
                        </Typography>
                      )}
                    </Grid>
                    
                    {/* Show plots for completed measurements */}
                    {currentMeasurement.status === 'completed' && (
                      <>
                        {/* Ionic Conductivity Plot */}
                        <Grid item xs={12}>
                          <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Timeline color="primary" />
                            Ionic Conductivity Results
                          </Typography>
                          {plotLoading ? (
                            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                              <CircularProgress />
                              <Typography variant="body2" sx={{ ml: 2 }}>
                                Loading ionic plot data...
                              </Typography>
                            </Box>
                          ) : plotError ? (
                            <Alert severity="error">
                              {plotError}
                            </Alert>
                          ) : plotData ? (
                            <SafePlotComponent plotData={plotData} sampleId={currentMeasurement.sample_id} />
                          ) : (
                            <Alert severity="warning">
                              No ionic conductivity plot data available for this measurement.
                            </Alert>
                          )}
                        </Grid>

                        {/* Electronic Conductivity Plot */}
                        {currentMeasurement.include_electronic_conductivity && (
                          <Grid item xs={12}>
                            <Typography variant="h6" sx={{ mb: 1, mt: 3, display: 'flex', alignItems: 'center', gap: 1 }}>
                              <AutoGraph color="primary" />
                              Electronic Conductivity Results
                            </Typography>
                            {currentMeasurement.electronic_conductivity_params && (
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 3, bgcolor: 'grey.100', px: 2, py: 1, borderRadius: 1, mb: 2 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                  <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 'bold' }}>
                                    Measurement Voltages:
                                  </Typography>
                                  <Typography variant="body2" sx={{ fontFamily: 'monospace', color: 'primary.main', fontWeight: 'bold' }}>
                                    {currentMeasurement.electronic_conductivity_params.voltages.join(', ')} V
                                  </Typography>
                                </Box>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                  <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 'bold' }}>
                                    Durations:
                                  </Typography>
                                  <Typography variant="body2" sx={{ fontFamily: 'monospace', color: 'secondary.main', fontWeight: 'bold' }}>
                                    {currentMeasurement.electronic_conductivity_params.durations.join(', ')} s
                                  </Typography>
                                </Box>
                              </Box>
                            )}
                            {electronicPlotLoading ? (
                              <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                                <CircularProgress />
                                <Typography variant="body2" sx={{ ml: 2 }}>
                                  Loading electronic plot data...
                                </Typography>
                              </Box>
                            ) : electronicPlotError ? (
                              <Alert severity="error">
                                {electronicPlotError}
                              </Alert>
                            ) : electronicPlotData ? (
                              <SafePlotComponent plotData={electronicPlotData} sampleId={currentMeasurement.sample_id} />
                            ) : (
                              <Alert severity="warning">
                                No electronic conductivity plot data available for this measurement.
                              </Alert>
                            )}
                          </Grid>
                        )}
                      </>
                    )}
                  </Grid>
                </CardContent>
              </Card>
            )}
        </Grid>
      </Grid>

      {/* Measurement Selection Dialog */}
      <Dialog
        open={measurementSelectionOpen}
        onClose={handleMeasurementSelectionCancel}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Timeline color="primary" />
            Select Measurements to Load
          </Box>
        </DialogTitle>
        
        <DialogContent>
          <Typography variant="body1" sx={{ mb: 3 }}>
            This sample has multiple measurements. Please select which ones to load:
          </Typography>
          
          {sampleMeasurements && (
            <Grid container spacing={3}>
              {/* Ionic Conductivity Selection */}
              {sampleMeasurements.ionic_conductivity_measurements?.length > 0 && (
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel>Ionic Conductivity Measurement</InputLabel>
                    <Select
                      value={selectedIonicMeasurement}
                      label="Ionic Conductivity Measurement"
                      onChange={(e) => setSelectedIonicMeasurement(e.target.value)}
                    >
                      {sampleMeasurements.ionic_conductivity_measurements.map((measurement) => (
                        <MenuItem key={measurement.measurement_id} value={measurement.measurement_id}>
                          <Box>
                            <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                              {new Date(measurement.timestamp).toLocaleString()}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              ID: {measurement.measurement_id}
                            </Typography>
                            {measurement.sample_height_mm && (
                              <Typography variant="caption" sx={{ display: 'block' }}>
                                Height: {measurement.sample_height_mm} mm
                              </Typography>
                            )}
                          </Box>
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
              )}

              {/* Electronic Conductivity Selection */}
              {sampleMeasurements.electronic_conductivity_measurements?.length > 0 && (
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel>Electronic Conductivity Measurement</InputLabel>
                    <Select
                      value={selectedElectronicMeasurement}
                      label="Electronic Conductivity Measurement"
                      onChange={(e) => setSelectedElectronicMeasurement(e.target.value)}
                    >
                      {sampleMeasurements.electronic_conductivity_measurements.map((measurement) => (
                        <MenuItem key={measurement.measurement_id} value={measurement.measurement_id}>
                          <Box>
                            <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                              {new Date(measurement.timestamp).toLocaleString()}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              ID: {measurement.measurement_id}
                            </Typography>
                            {measurement.sample_height_mm && (
                              <Typography variant="caption" sx={{ display: 'block' }}>
                                Height: {measurement.sample_height_mm} mm
                              </Typography>
                            )}
                          </Box>
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
              )}
            </Grid>
          )}
        </DialogContent>
        
        <DialogActions>
          <Button onClick={handleMeasurementSelectionCancel}>
            Cancel
          </Button>
          <Button 
            onClick={handleMeasurementSelectionConfirm} 
            variant="contained" 
            color="primary"
            disabled={loading}
            startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <Timeline />}
          >
            {loading ? 'Loading...' : 'Load Selected Measurements'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* QR Scanner Dialog */}
      <Dialog 
        open={qrScannerOpen} 
        onClose={handleCloseQrScanner} 
        maxWidth="sm" 
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <QrCodeScanner color="primary" />
            QR Code Scanner
          </Box>
          <IconButton onClick={handleCloseQrScanner}>
            <Close />
          </IconButton>
        </DialogTitle>
        
        <DialogContent sx={{ p: 0, position: 'relative', minHeight: 400 }}>
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            style={{
              width: '100%',
              height: '400px',
              objectFit: 'cover',
              display: qrError ? 'none' : 'block',
              backgroundColor: 'black'
            }}
          />
          
          {qrScanning && (
            <Box sx={{ 
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              display: 'flex', 
              flexDirection: 'column', 
              alignItems: 'center', 
              justifyContent: 'center',
              backgroundColor: 'rgba(0, 0, 0, 0.8)',
              color: 'white',
              zIndex: 1
            }}>
              <CircularProgress sx={{ color: '#00ff88', mb: 2 }} size={60} />
              <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
                Starting camera...
              </Typography>
            </Box>
          )}
          
          {qrError && (
            <Box sx={{ 
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white', 
              p: 4, 
              textAlign: 'center',
              minHeight: 400,
              background: 'linear-gradient(135deg, #333 0%, #111 100%)'
            }}>
              <Error sx={{ fontSize: 60, color: '#ff6b6b', mb: 2 }} />
              <Typography variant="h6" color="#ff6b6b" gutterBottom sx={{ fontWeight: 'bold' }}>
                Camera Error
              </Typography>
              <Typography sx={{ mb: 3, opacity: 0.8 }}>
                {qrError}
              </Typography>
              <Button 
                variant="contained" 
                onClick={handleCloseQrScanner} 
                sx={{ 
                  borderRadius: 3,
                  px: 4,
                  py: 1.5,
                  background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
                }}
              >
                Close
              </Button>
            </Box>
          )}
        </DialogContent>
        
        <Box sx={{ 
          bgcolor: 'black', 
          p: 3, 
          borderTop: '1px solid rgba(255,255,255,0.1)'
        }}>
          <Typography sx={{ 
            color: '#00ff88', 
            textAlign: 'center', 
            fontWeight: 'bold',
            fontSize: '1rem'
          }}>
            Point camera at QR code - entire view is scanned
          </Typography>
        </Box>
              </Dialog>

      {/* Add CSS for animations */}
      <style jsx global>{`
        @keyframes shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
        @keyframes scanPulse {
          0% { opacity: 1; }
          50% { opacity: 0.5; }
          100% { opacity: 1; }
        }
      `}</style>
    </Container>
  );
};

export default IonicConductivityPage; 