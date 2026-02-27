import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Typography,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Button,
  Chip,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Alert,
  CircularProgress
} from '@mui/material';
import CleaningServicesIcon from '@mui/icons-material/CleaningServices';
import { getConsumableRackSlots, cleanConsumableRackSlot, cleanConsumableRackLevel } from '../api/api';

// Status color mapping
const statusColors = {
  available: '#4caf50', // green
  dirty: '#ff9800',     // orange
  empty: '#9e9e9e',     // grey
};

const ConsumableStatusDot = ({ type, status }) => (
  <Tooltip
    title={`${type}: ${status}`}
    placement="top"
    arrow
  >
    <Box
      component="span"
      sx={{
        width: 12,
        height: 12,
        borderRadius: '50%',
        display: 'inline-block',
        backgroundColor: statusColors[status] || '#9e9e9e',
        mx: 0.5,
      }}
    />
  </Tooltip>
);

const slotStatusColor = {
  filled: 'success',
  in_use: 'warning',
  wait_for_removal: 'error',
};

const ConsumableRackPage = () => {
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [selectedLevel, setSelectedLevel] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [levelDialogOpen, setLevelDialogOpen] = useState(false);
  const [actionSuccess, setActionSuccess] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const previousSlotsRef = useRef([]);

  const fetchSlots = async (isInitialLoad = false) => {
    try {
      // Only set loading to true on initial load
      if (isInitialLoad) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }
      
      const data = await getConsumableRackSlots();
      
      // Check if data has changed before updating state
      const hasChanged = JSON.stringify(data) !== JSON.stringify(previousSlotsRef.current);
      
      if (hasChanged) {
        setSlots(data);
        previousSlotsRef.current = data;
      }
      
      setError(null);
    } catch (err) {
      console.error('Error fetching slots:', err);
      setError(err.message || 'Failed to fetch consumable rack slots');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    // Initial load
    fetchSlots(true);
    
    // Set up auto-refresh every 5 seconds
    const intervalId = setInterval(() => fetchSlots(false), 5000);
    
    // Cleanup interval on component unmount
    return () => clearInterval(intervalId);
  }, []);

  const handleCleanSlot = (level, row) => {
    setSelectedSlot({ level, row });
    setDialogOpen(true);
  };

  const confirmCleanSlot = async () => {
    try {
      await cleanConsumableRackSlot(selectedSlot.level, selectedSlot.row);
      await fetchSlots();
      setActionSuccess(true);
      setActionError(null);
    } catch (err) {
      console.error('Error cleaning slot:', err);
      setActionError(err.message || 'Failed to clean slot');
      setActionSuccess(false);
    }
    setDialogOpen(false);
  };

  const handleCleanLevel = (level) => {
    setSelectedLevel(level);
    setLevelDialogOpen(true);
  };

  const confirmCleanLevel = async () => {
    try {
      await cleanConsumableRackLevel(selectedLevel);
      await fetchSlots();
      setActionSuccess(true);
      setActionError(null);
    } catch (err) {
      console.error('Error cleaning level:', err);
      setActionError(err.message || 'Failed to clean level');
      setActionSuccess(false);
    }
    setLevelDialogOpen(false);
  };

  const groupSlotsByLevel = () => {
    const groups = {};
    slots.forEach(slot => {
      if (!groups[slot.level]) groups[slot.level] = [];
      groups[slot.level].push(slot);
    });
    return groups;
  };

  const isLevelReadyForCleaning = (levelSlots) => {
    return levelSlots.length > 0 && levelSlots.every(slot => slot.slot_status === 'wait_for_removal');
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  const slotGroups = groupSlotsByLevel();

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Consumable Rack
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
          
          {Object.entries(slotGroups).map(([level, levelSlots]) => (
            <Paper key={level} sx={{ mb: 3, overflow: 'hidden' }}>
              <Box sx={{ 
                bgcolor: 'primary.main', 
                color: 'primary.contrastText', 
                px: 2, 
                py: 1,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <Typography variant="h6">
                  Level {level}
                </Typography>
                {isLevelReadyForCleaning(levelSlots) && (
                  <Button
                    variant="contained"
                    color="secondary"
                    size="small"
                    startIcon={<CleaningServicesIcon />}
                    onClick={() => handleCleanLevel(level)}
                  >
                    Clean Level
                  </Button>
                )}
              </Box>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Row</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Sample</TableCell>
                      <TableCell>Consumables Status</TableCell>
                      <TableCell align="right">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {levelSlots.sort((a, b) => a.row - b.row).map((slot) => (
                      <TableRow key={`${slot.level}_${slot.row}`}>
                        <TableCell>{slot.row}</TableCell>
                        <TableCell>
                          <Chip
                            label={slot.slot_status}
                            color={slotStatusColor[slot.slot_status]}
                            size="small"
                          />
                        </TableCell>
                        <TableCell>
                          {slot.sample_name ? (
                            <Box>
                              <Typography variant="body2">{slot.sample_name}</Typography>
                              {slot.sample_id && (
                                <Typography variant="caption" color="text.secondary">
                                  ID: {slot.sample_id}
                                </Typography>
                              )}
                            </Box>
                          ) : (
                            slot.sample_id || '-'
                          )}
                        </TableCell>
                        <TableCell>
                          {Object.entries(slot.consumable_status).map(([type, status]) => (
                            <ConsumableStatusDot key={type} type={type} status={status} />
                          ))}
                        </TableCell>
                        <TableCell align="right">
                          {slot.slot_status === 'wait_for_removal' && (
                            <Button
                              variant="contained"
                              color="primary"
                              size="small"
                              startIcon={<CleaningServicesIcon />}
                              onClick={() => handleCleanSlot(slot.level, slot.row)}
                            >
                              Clean
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
          ))}
        </Box>
      )}

      {/* Clean Slot Dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)}>
        <DialogTitle>Clean Slot</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to clean this slot? This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button onClick={confirmCleanSlot} color="primary" variant="contained">
            Clean
          </Button>
        </DialogActions>
      </Dialog>

      {/* Clean Level Dialog */}
      <Dialog open={levelDialogOpen} onClose={() => setLevelDialogOpen(false)}>
        <DialogTitle>Clean Level</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to clean all slots in Level {selectedLevel}? This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLevelDialogOpen(false)}>Cancel</Button>
          <Button onClick={confirmCleanLevel} color="primary" variant="contained">
            Clean Level
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ConsumableRackPage; 