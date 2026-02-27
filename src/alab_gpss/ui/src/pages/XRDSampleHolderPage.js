import React, { useState, useEffect, useRef } from 'react';
import { 
  Typography, 
  Grid, 
  Card, 
  CardContent, 
  Button, 
  Box,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Alert,
  DialogContentText,
  IconButton,
  Tooltip,
  Paper,
  Divider,
  CircularProgress
} from '@mui/material';
import BlockIcon from '@mui/icons-material/Block';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import CleaningServicesIcon from '@mui/icons-material/CleaningServices';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import LinearProgress from '@mui/material/LinearProgress';
import { 
  getXRDSampleHolderSlots, 
  markXRDSampleHolderAsClean, 
  disableXRDSampleHolderSlot, 
  enableXRDSampleHolderSlot,
  cleanXRDSampleHolderRow,
  disableXRDSampleHolderRow,
  enableXRDSampleHolderRow,
  runXRDMeasurement,
  getXRDMeasurementProgress
} from '../api/api';

const XRDSampleHolderPage = () => {
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [disableDialogOpen, setDisableDialogOpen] = useState(false);
  const [enableDialogOpen, setEnableDialogOpen] = useState(false);
  const [actionSuccess, setActionSuccess] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [selectedRow, setSelectedRow] = useState(null);
  const [rowActionType, setRowActionType] = useState(null);
  const [rowDialogOpen, setRowDialogOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const previousSlotsRef = useRef([]);
  
  // XRD Measurement states
  const [measurementProgress, setMeasurementProgress] = useState({
    is_running: false,
    row: null,
    progress: 0,
    current_slot: null,
    total_slots: 0,
    status: "idle",
    completed_at: null,
    success: null
  });
  const [runMeasurementDialogOpen, setRunMeasurementDialogOpen] = useState(false);

  const fetchSlots = async (isInitialLoad = false) => {
    try {
      // Only set loading to true on initial load
      if (isInitialLoad) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }
      
      const data = await getXRDSampleHolderSlots();
      
      // Check if data has changed before updating state
      const hasChanged = JSON.stringify(data) !== JSON.stringify(previousSlotsRef.current);
      
      if (hasChanged) {
        setSlots(data);
        previousSlotsRef.current = data;
      }
      
      setError(null);
    } catch (err) {
      console.error('Error fetching slots:', err);
      setError(err.message || err.response?.data?.detail || 'Failed to fetch XRD sample holder slots');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const fetchMeasurementProgress = async () => {
    try {
      const progress = await getXRDMeasurementProgress();
      setMeasurementProgress(progress);
      
      // Save to localStorage when measurement is completed (success or failure)
      if (!progress.is_running && (progress.completed_at || progress.success !== null)) {
        localStorage.setItem('xrd_last_measurement_result', JSON.stringify(progress));
      }
      
      // If a measurement is currently running, clear any old saved results
      if (progress.is_running) {
        localStorage.removeItem('xrd_last_measurement_result');
      }
    } catch (err) {
      console.error('Error fetching measurement progress:', err);
    }
  };

  // Load saved measurement result from localStorage on component mount
  const loadSavedMeasurementResult = () => {
    try {
      const saved = localStorage.getItem('xrd_last_measurement_result');
      if (saved) {
        const savedResult = JSON.parse(saved);
        
        // Check if this is a completed measurement (has success status or completed_at)
        if (savedResult.success !== null || savedResult.completed_at) {
          // Check age if completed_at exists
          if (savedResult.completed_at) {
            const completedAt = new Date(savedResult.completed_at);
            const now = new Date();
            const hoursDiff = (now - completedAt) / (1000 * 60 * 60);
            
            if (hoursDiff < 24) {
              setMeasurementProgress(prev => ({
                ...prev,
                ...savedResult
              }));
            } else {
              // Remove old results
              localStorage.removeItem('xrd_last_measurement_result');
            }
          } else {
            // If no completed_at but has success status, load it anyway (recent error case)
            setMeasurementProgress(prev => ({
              ...prev,
              ...savedResult
            }));
          }
        }
      }
    } catch (err) {
      console.error('Error loading saved measurement result:', err);
      localStorage.removeItem('xrd_last_measurement_result');
    }
  };

  useEffect(() => {
    // Load saved measurement result first
    loadSavedMeasurementResult();
    
    // Initial load
    fetchSlots(true);
    fetchMeasurementProgress();
    
    // Set up auto-refresh every 5 seconds
    const intervalId = setInterval(() => {
      fetchSlots(false);
      fetchMeasurementProgress();
    }, 5000);
    
    // Cleanup interval on component unmount
    return () => clearInterval(intervalId);
  }, []);

  const handleMarkAsClean = async (slot) => {
    setSelectedSlot(slot);
    setDialogOpen(true);
  };

  const confirmMarkAsClean = async () => {
    try {
      await markXRDSampleHolderAsClean(selectedSlot);
      await fetchSlots(); // Fetch first to ensure we have latest data
      setActionSuccess(true);
      setActionError(null);
    } catch (err) {
      console.error('Error marking as clean:', err);
      setActionError(err.message || err.response?.data?.detail || 'Failed to mark slot as clean');
      setActionSuccess(false);
    }
    setDialogOpen(false);
  };

  const handleDisable = async (slot) => {
    setSelectedSlot(slot);
    setDisableDialogOpen(true);
  };

  const confirmDisable = async () => {
    try {
      await disableXRDSampleHolderSlot(selectedSlot);
      await fetchSlots(); // Fetch first to ensure we have latest data
      setActionSuccess(true);
      setActionError(null);
    } catch (err) {
      console.error('Error disabling slot:', err);
      setActionError(err.message || err.response?.data?.detail || 'Failed to disable slot');
      setActionSuccess(false);
    }
    setDisableDialogOpen(false);
  };

  const handleEnable = async (slot) => {
    setSelectedSlot(slot);
    setEnableDialogOpen(true);
  };

  const confirmEnable = async () => {
    try {
      await enableXRDSampleHolderSlot(selectedSlot);
      await fetchSlots();
      setActionSuccess(true);
      setActionError(null);
    } catch (err) {
      console.error('Error enabling slot:', err);
      setActionError(err.message || err.response?.data?.detail || 'Failed to enable slot');
      setActionSuccess(false);
    }
    setEnableDialogOpen(false);
  };

  const handleRowAction = (row, actionType) => {
    setSelectedRow(row);
    setRowActionType(actionType);
    setRowDialogOpen(true);
  };

  const confirmRowAction = async () => {
    try {
      switch (rowActionType) {
        case 'clean':
          await cleanXRDSampleHolderRow(selectedRow);
          break;
        case 'disable':
          await disableXRDSampleHolderRow(selectedRow);
          break;
        case 'enable':
          await enableXRDSampleHolderRow(selectedRow);
          break;
      }
      await fetchSlots();
      setActionSuccess(true);
      setActionError(null);
    } catch (err) {
      console.error('Error performing row action:', err);
      setActionError(err.message || err.response?.data?.detail || `Failed to ${rowActionType} row`);
      setActionSuccess(false);
    }
    setRowDialogOpen(false);
  };

  const handleRunMeasurement = (row) => {
    setSelectedRow(row);
    setRowActionType('run_measurement');
    setRunMeasurementDialogOpen(true);
  };

  const confirmRunMeasurement = async () => {
    try {
      // Clear any previous measurement result when starting a new one
      localStorage.removeItem('xrd_last_measurement_result');
      
      await runXRDMeasurement(selectedRow);
      setActionSuccess(true);
      setActionError(null);
      // Immediately fetch progress to update UI
      await fetchMeasurementProgress();
    } catch (err) {
      console.error('Error starting measurement:', err);
      setActionError(err.message || err.response?.data?.detail || 'Failed to start measurement');
      setActionSuccess(false);
    }
    setRunMeasurementDialogOpen(false);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'clean':
        return 'success';
      case 'in_use':
        return 'warning';
      case 'loaded':
        return 'error';
      case 'disabled':
        return 'default';
      default:
        return 'default';
    }
  };

  const groupSlotsByRow = () => {
    const groups = {};
    // Ensure slots is an array before calling forEach
    if (Array.isArray(slots)) {
      slots.forEach(slot => {
        const row = slot.slot[0];
        if (!groups[row]) groups[row] = [];
        groups[row].push(slot);
      });
    } else {
      console.error('Slots is not an array:', slots);
    }
    return groups;
  };

  const canCleanRow = (rowSlots) => {
    return rowSlots.every(slot => slot.status === 'loaded');
  };

  const canDisableRow = (rowSlots) => {
    return rowSlots.every(slot => slot.status === 'clean');
  };

  const canEnableRow = (rowSlots) => {
    return rowSlots.every(slot => slot.status === 'disabled');
  };

  const canRunMeasurement = (rowSlots) => {
    // Can run measurement if:
    // 1. There are samples in the row
    // 2. No measurement is currently running
    // 3. All slots are either "loaded" or "clean" (not being used)
    const hasSamples = rowSlots.some(slot => slot.sample_id !== null);
    const allSlotsAvailable = rowSlots.every(slot => 
      slot.status === 'loaded' || slot.status === 'clean' || slot.status === 'disabled'
    );
    return hasSamples && !measurementProgress.is_running && allSlotsAvailable;
  };

  const getRowActionMessage = () => {
    switch (rowActionType) {
      case 'clean':
        return `Are you sure you want to clean all slots in row ${selectedRow}?`;
      case 'disable':
        return `Are you sure you want to disable all slots in row ${selectedRow}?`;
      case 'enable':
        return `Are you sure you want to enable all slots in row ${selectedRow}?`;
      default:
        return '';
    }
  };

  const slotGroups = groupSlotsByRow();

  if (loading) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography>Loading...</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        XRD Sample Holder
      </Typography>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      {actionSuccess && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setActionSuccess(false)}>
          Action completed successfully
        </Alert>
      )}
      {actionError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
          {actionError}
        </Alert>
      )}
      {/* Persistent XRD Measurement Status Bar */}
      <Paper sx={{ 
        p: 2, 
        mb: 2, 
        border: measurementProgress.is_running 
          ? '2px solid #1976d2' 
          : measurementProgress.success === true 
            ? '2px solid #4caf50' 
            : measurementProgress.success === false 
              ? '2px solid #f44336'
              : '1px solid #e0e0e0',
        bgcolor: measurementProgress.is_running 
          ? 'rgba(25, 118, 210, 0.05)' 
          : measurementProgress.success === true 
            ? 'rgba(76, 175, 80, 0.05)' 
            : measurementProgress.success === false 
              ? 'rgba(244, 67, 54, 0.05)'
              : 'background.paper'
      }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          {measurementProgress.is_running ? (
            `🔬 XRD Measurement in Progress - Row ${measurementProgress.row}`
          ) : measurementProgress.success === true ? (
            `✅ XRD Measurement Completed - Row ${measurementProgress.row}`
          ) : measurementProgress.success === false ? (
            `❌ XRD Measurement Failed - Row ${measurementProgress.row}`
          ) : (
            '📊 XRD Measurement Status'
          )}
        </Typography>
        
        {measurementProgress.is_running ? (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {measurementProgress.status}
              {measurementProgress.current_slot && ` (Current: ${measurementProgress.current_slot})`}
            </Typography>
            <LinearProgress 
              variant="determinate" 
              value={measurementProgress.progress} 
              sx={{ mb: 1 }}
            />
            <Typography variant="body2" color="text.secondary">
              Progress: {measurementProgress.progress}% ({measurementProgress.total_slots} samples)
            </Typography>
          </>
        ) : measurementProgress.success !== null ? (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Status: {measurementProgress.status}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {measurementProgress.completed_at 
                ? `Completed: ${new Date(measurementProgress.completed_at).toLocaleString()}` 
                : 'Status recorded'
              }
              {measurementProgress.total_slots > 0 && ` (${measurementProgress.total_slots} samples)`}
            </Typography>
          </>
        ) : (
          <Typography variant="body2" color="text.secondary">
            No recent XRD measurements. Start a measurement by clicking "Run Measurement" on any row with samples.
          </Typography>
        )}
      </Paper>
      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Box sx={{ position: 'relative' }}>
          {refreshing && (
            <Box sx={{ 
              position: 'absolute', 
              top: 10, 
              right: 10, 
              zIndex: 1 
            }}>
              <CircularProgress size={24} />
            </Box>
          )}
          {Object.entries(slotGroups).map(([row, rowSlots]) => (
            <Paper key={row} sx={{ mb: 2, p: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Typography variant="h6" sx={{ flexGrow: 1 }}>
                  Row {row}
                </Typography>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  {canRunMeasurement(rowSlots) && (
                    <Button
                      variant="contained"
                      color="secondary"
                      size="small"
                      startIcon={<PlayArrowIcon />}
                      onClick={() => handleRunMeasurement(row)}
                      disabled={measurementProgress.is_running}
                    >
                      Run Measurement
                    </Button>
                  )}
                  {canCleanRow(rowSlots) && (
                    <Button
                      variant="contained"
                      color="primary"
                      size="small"
                      startIcon={<CleaningServicesIcon />}
                      onClick={() => handleRowAction(row, 'clean')}
                      disabled={measurementProgress.is_running && measurementProgress.row === row}
                    >
                      Clean Row
                    </Button>
                  )}
                  {canDisableRow(rowSlots) && (
                    <Button
                      variant="contained"
                      color="error"
                      size="small"
                      startIcon={<BlockIcon />}
                      onClick={() => handleRowAction(row, 'disable')}
                      disabled={measurementProgress.is_running && measurementProgress.row === row}
                    >
                      Disable Row
                    </Button>
                  )}
                  {canEnableRow(rowSlots) && (
                    <Button
                      variant="contained"
                      color="success"
                      size="small"
                      startIcon={<CheckCircleOutlineIcon />}
                      onClick={() => handleRowAction(row, 'enable')}
                      disabled={measurementProgress.is_running && measurementProgress.row === row}
                    >
                      Enable Row
                    </Button>
                  )}
                </Box>
              </Box>
              <Grid container spacing={1}>
                {rowSlots.map((slot) => (
                  <Grid item xs={12} sm={6} md={3} key={slot.slot}>
                    <Card
                      sx={{
                        height: 180,
                        display: 'flex',
                        flexDirection: 'column',
                        position: 'relative',
                        border: slot.status === 'in_use' ? '2px solid #1976d2' : '1px solid rgba(0, 0, 0, 0.12)',
                        boxShadow: slot.status === 'in_use' ? '0 4px 8px rgba(0, 0, 0, 0.2)' : '0 2px 4px rgba(0, 0, 0, 0.1)',
                        bgcolor: slot.status === 'disabled' ? 'rgba(0, 0, 0, 0.04)' : 'background.paper',
                      }}
                    >
                      <CardContent sx={{ pb: 0, pt: 1, px: 1.5 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                          <Typography variant="h6" sx={{ fontSize: '1.1rem' }}>
                            Slot {slot.slot}
                          </Typography>
                          {slot.status === 'clean' && (
                            <Tooltip title="Disable Slot">
                              <IconButton
                                size="small"
                                onClick={() => handleDisable(slot.slot)}
                                disabled={measurementProgress.is_running && measurementProgress.row === slot.slot[0]}
                                sx={{ 
                                  color: 'action.active',
                                  '&:hover': {
                                    color: 'error.main'
                                  }
                                }}
                              >
                                <BlockIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          )}
                          {slot.status === 'disabled' && (
                            <Tooltip title="Enable Slot">
                              <IconButton
                                size="small"
                                onClick={() => handleEnable(slot.slot)}
                                disabled={measurementProgress.is_running && measurementProgress.row === slot.slot[0]}
                                sx={{ 
                                  color: 'action.active',
                                  '&:hover': {
                                    color: 'success.main'
                                  }
                                }}
                              >
                                <CheckCircleOutlineIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          )}
                        </Box>
                        <Chip
                          label={slot.status}
                          color={getStatusColor(slot.status)}
                          size="small"
                          sx={{ mb: 0.5 }}
                        />
                        {slot.sample_name && (
                          <Box sx={{ mt: 0.5 }}>
                            <Typography variant="body2" color="text.secondary" sx={{ mb: 0.25 }}>
                              Sample: {slot.sample_name}
                            </Typography>
                            {slot.sample_id && (
                              <Typography variant="body2" color="text.secondary">
                                ID: {slot.sample_id}
                              </Typography>
                            )}
                          </Box>
                        )}
                        {(slot.status === 'loaded' || slot.status === 'in_use') && slot.sample_id && !slot.sample_name && (
                          <Box sx={{ mt: 0.5 }}>
                            <Typography variant="body2" color="text.secondary" sx={{ mb: 0.25 }}>
                              Sample ID: {slot.sample_id}
                            </Typography>
                          </Box>
                        )}
                      </CardContent>
                      <Box sx={{ px: 1.5, pb: 1, pt: 0.5, mt: 'auto', backgroundColor: 'rgba(0, 0, 0, 0.02)' }}>
                        {slot.status === 'loaded' && (
                          <Button
                            variant="contained"
                            color="primary"
                            size="small"
                            onClick={() => handleMarkAsClean(slot.slot)}
                            fullWidth
                            disabled={measurementProgress.is_running && measurementProgress.row === slot.slot[0]}
                            sx={{ 
                              fontWeight: 'bold',
                              py: 0.5,
                              backgroundColor: '#1976d2',
                              '&:hover': {
                                backgroundColor: '#1565c0'
                              }
                            }}
                          >
                            Mark as Clean
                          </Button>
                        )}
                      </Box>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </Paper>
          ))}
        </Box>
      )}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)}>
        <DialogTitle>Confirm Action</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to mark slot {selectedSlot} as clean?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button onClick={confirmMarkAsClean} color="primary">
            Confirm
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={disableDialogOpen} onClose={() => setDisableDialogOpen(false)}>
        <DialogTitle>Confirm Action</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to disable slot {selectedSlot}? This will mark it as unavailable for use.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDisableDialogOpen(false)}>Cancel</Button>
          <Button onClick={confirmDisable} color="error">
            Disable
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={enableDialogOpen} onClose={() => setEnableDialogOpen(false)}>
        <DialogTitle>Confirm Action</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to enable slot {selectedSlot}? This will mark it as clean and available for use.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEnableDialogOpen(false)}>Cancel</Button>
          <Button onClick={confirmEnable} color="success">
            Enable
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={rowDialogOpen} onClose={() => setRowDialogOpen(false)}>
        <DialogTitle>Confirm Action</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {getRowActionMessage()}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRowDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={confirmRowAction} 
            color={rowActionType === 'disable' ? 'error' : rowActionType === 'enable' ? 'success' : 'primary'}
          >
            Confirm
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={runMeasurementDialogOpen} onClose={() => setRunMeasurementDialogOpen(false)}>
        <DialogTitle>Confirm XRD Measurement</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to start XRD measurement for all samples in row {selectedRow}?
          </DialogContentText>
          <DialogContentText sx={{ mt: 1, fontWeight: 'bold', color: 'warning.main' }}>
            This process will take several minutes and cannot be interrupted once started.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRunMeasurementDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={confirmRunMeasurement} 
            color="secondary"
            variant="contained"
          >
            Start Measurement
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default XRDSampleHolderPage; 