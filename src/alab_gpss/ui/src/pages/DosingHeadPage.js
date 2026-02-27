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
  Paper,
  CircularProgress
} from '@mui/material';
import {
  getDosingHeads,
  addDosingHead,
  clearDosingHeadError,
  unloadDosingHead,
} from '../api/api';

const DosingHeadPage = () => {
  const [heads, setHeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedHead, setSelectedHead] = useState(null);
  const [openDialog, setOpenDialog] = useState(false);
  const [chemical, setChemical] = useState('');
  const [actionSuccess, setActionSuccess] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const previousHeadsRef = useRef([]);

  const fetchHeads = async (isInitialLoad = false) => {
    try {
      // Only set loading to true on initial load
      if (isInitialLoad) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }
      
      const data = await getDosingHeads();
      
      // Check if data has changed before updating state
      const hasChanged = JSON.stringify(data) !== JSON.stringify(previousHeadsRef.current);
      
      if (hasChanged) {
        setHeads(data);
        previousHeadsRef.current = data;
      }
      
      setError(null);
    } catch (err) {
      setError('Failed to fetch dosing heads');
      console.error(err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    // Initial load
    fetchHeads(true);
    
    // Set up auto-refresh every 5 seconds
    const intervalId = setInterval(() => fetchHeads(false), 5000);
    
    // Cleanup interval on component unmount
    return () => clearInterval(intervalId);
  }, []);

  const handleAddChemical = (slot) => {
    setSelectedHead(slot);
    setOpenDialog(true);
  };

  const handleClearError = async (slot) => {
    try {
      await clearDosingHeadError(slot);
      setActionSuccess(true);
      setActionError(null);
      fetchHeads();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to clear error');
      setActionSuccess(false);
    }
  };

  const handleUnload = async (slot) => {
    try {
      await unloadDosingHead(slot);
      setActionSuccess(true);
      setActionError(null);
      fetchHeads();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to unload dosing head');
      setActionSuccess(false);
    }
  };

  const confirmAddChemical = async () => {
    try {
      await addDosingHead(selectedHead, chemical);
      setActionSuccess(true);
      setActionError(null);
      setChemical('');
      fetchHeads();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to add chemical');
      setActionSuccess(false);
    }
    setOpenDialog(false);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setChemical('');
    setActionSuccess(false);
    setActionError(null);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'normal':
        return 'success';
      case 'stuck':
        return 'error';
      case 'empty':
        return 'warning';
      case 'in_use':
        return 'info';
      default:
        return 'default';
    }
  };

  // Group heads by row (1-14) and level (A-D)
  const groupedHeads = {};
  heads.forEach(head => {
    const [row, level] = head.slot.match(/(\d+)([A-D])/).slice(1);
    if (!groupedHeads[row]) {
      groupedHeads[row] = {};
    }
    groupedHeads[row][level] = head;
  });

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Dosing Head
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
          
          {Object.entries(groupedHeads).map(([row, levelHeads]) => (
            <Paper key={row} sx={{ p: 2, mb: 2 }}>
              <Typography variant="h6" style={{ fontWeight: '500' }} gutterBottom>
                Row {row}
              </Typography>
              <Grid container spacing={2}>
                {['A', 'B', 'C', 'D'].map(level => {
                  const head = levelHeads[level];
                  return (
                    <Grid item xs={12} sm={6} md={3} key={`${row}${level}`}>
                      <Card
                        sx={{
                          height: '150px',
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'space-between',
                          border: head && head.status === 'in_use' 
                            ? '3px solid #1976d2' 
                            : head ? '2px solid #e0e0e0' : '2px solid #e0e0e0',
                          boxShadow: head && head.status === 'in_use' ? 3 : 1,
                        }}
                      >
                        <CardContent
                          sx={{
                            flexGrow: 1,
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'space-between',
                            p: 1.5,
                          }}
                        >
                          <Box>
                            <Box
                              sx={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                mb: 1,
                              }}
                            >
                              <Typography variant="subtitle2" component="div">
                                Level {level}
                              </Typography>
                              {head && (
                                <Chip
                                  label={head.status}
                                  color={getStatusColor(head.status)}
                                  size="small"
                                />
                              )}
                            </Box>
                            {head && head.chemical && (
                              <Typography
                                variant="h6"
                                component="div"
                                sx={{
                                  color: 'primary.main',
                                  fontWeight: 'bold',
                                  textAlign: 'center',
                                  my: 0.5,
                                  fontSize: '1.5rem',
                                  lineHeight: 2,
                                }}
                              >
                                {head.chemical}
                              </Typography>
                            )}
                          </Box>
                          <Box sx={{ mt: 'auto', display: 'flex', justifyContent: 'center', gap: 1 }}>
                            {head && (head.status === 'empty' || head.status === 'stuck') && (
                              <Button
                                variant="contained"
                                color="error"
                                onClick={() => handleClearError(head.slot)}
                                fullWidth
                                size="small"
                              >
                                Clear Error
                              </Button>
                            )}
                            {head && head.status === 'normal' && !head.chemical && (
                              <Button
                                variant="contained"
                                color="primary"
                                onClick={() => handleAddChemical(head.slot)}
                                fullWidth
                                size="small"
                              >
                                Add Chemical
                              </Button>
                            )}
                            {head && head.status === 'normal' && head.chemical && (
                              <Button
                                variant="contained"
                                color="warning"
                                onClick={() => handleUnload(head.slot)}
                                fullWidth
                                size="small"
                              >
                                Remove Chemical
                              </Button>
                            )}
                          </Box>
                        </CardContent>
                      </Card>
                    </Grid>
                  );
                })}
              </Grid>
            </Paper>
          ))}
        </Box>
      )}

      <Dialog open={openDialog} onClose={handleCloseDialog}>
        <DialogTitle>Add Chemical</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Chemical Name"
            type="text"
            fullWidth
            value={chemical}
            onChange={(e) => setChemical(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button onClick={confirmAddChemical} color="primary">
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default DosingHeadPage; 