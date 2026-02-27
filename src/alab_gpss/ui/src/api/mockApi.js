// Mock data for XRD sample holder
let mockXRDSampleHolderSlots = [
  {
    slot: "A1",
    status: "clean",
    sample_id: null,
    sample_name: null
  },
  {
    slot: "A2",
    status: "in_use",
    sample_id: "507f1f77bcf86cd799439011",
    sample_name: "Sample A"
  },
  {
    slot: "A3",
    status: "loaded",
    sample_id: "507f1f77bcf86cd799439012",
    sample_name: "Sample B"
  },
  {
    slot: "A4",
    status: "disabled",
    sample_id: null,
    sample_name: null
  },
  {
    slot: "B1",
    status: "clean",
    sample_id: null,
    sample_name: null
  },
  {
    slot: "B2",
    status: "in_use",
    sample_id: "507f1f77bcf86cd799439013",
    sample_name: "Sample C"
  },
  {
    slot: "B3",
    status: "loaded",
    sample_id: "507f1f77bcf86cd799439014",
    sample_name: "Sample D"
  },
  {
    slot: "B4",
    status: "disabled",
    sample_id: null,
    sample_name: null
  },
  {
    slot: "C1",
    status: "loaded",
    sample_id: "507f1f77bcf86cd799439015",
    sample_name: "Sample E"
  },
  {
    slot: "C2",
    status: "loaded",
    sample_id: "507f1f77bcf86cd799439016",
    sample_name: "Sample F"
  },
  {
    slot: "C3",
    status: "clean",
    sample_id: null,
    sample_name: null
  },
  {
    slot: "C4",
    status: "clean",
    sample_id: null,
    sample_name: null
  },
  {
    slot: "D1",
    status: "clean",
    sample_id: null,
    sample_name: null
  },
  {
    slot: "D2",
    status: "clean",
    sample_id: null,
    sample_name: null
  },
  {
    slot: "D3",
    status: "clean",
    sample_id: null,
    sample_name: null
  },
  {
    slot: "D4",
    status: "clean",
    sample_id: null,
    sample_name: null
  }
];

// Mock data for dosing heads
let mockDosingHeads = [
  {
    slot: "1A",
    status: "normal",
    chemical: "H2O"
  },
  {
    slot: "1B",
    status: "stuck",
    chemical: null
  },
  {
    slot: "1C",
    status: "empty",
    chemical: null
  },
  {
    slot: "1D",
    status: "in_use",
    chemical: "NaOH"
  }
];

// Mock data for consumable rack
let mockConsumableRackSlots = [
  {
    level: 1,
    row: 1,
    slot_status: "filled",
    sample_id: "507f1f77bcf86cd799439015",
    sample_name: "Sample E",
    consumable_status: {
      vial: "normal",
      cap: "normal"
    }
  },
  {
    level: 1,
    row: 2,
    slot_status: "empty",
    sample_id: null,
    sample_name: null,
    consumable_status: {
      vial: "available",
      cap: "available"
    }
  }
];

// Mock API functions
export const mockGetXRDSampleHolderSlots = () => {
  return Promise.resolve(mockXRDSampleHolderSlots);
};

export const mockGetXRDSampleHolderSlot = (slot) => {
  const foundSlot = mockXRDSampleHolderSlots.find((s) => s.slot === slot);
  if (!foundSlot) {
    return Promise.reject(new Error("Slot not found"));
  }
  return Promise.resolve(foundSlot);
};

export const mockMarkXRDSampleHolderAsClean = (slot) => {
  const slotIndex = mockXRDSampleHolderSlots.findIndex((s) => s.slot === slot);
  if (slotIndex === -1) {
    return Promise.reject(new Error("Slot not found"));
  }
  mockXRDSampleHolderSlots[slotIndex].status = "clean";
  mockXRDSampleHolderSlots[slotIndex].sample_id = null;
  mockXRDSampleHolderSlots[slotIndex].sample_name = null;
  return Promise.resolve({ message: `Slot ${slot} marked as clean` });
};

export const mockGetDosingHeads = () => {
  return Promise.resolve(mockDosingHeads);
};

export const mockGetDosingHead = (slot) => {
  const foundHead = mockDosingHeads.find((h) => h.slot === slot);
  if (!foundHead) {
    return Promise.reject(new Error("Dosing head not found"));
  }
  return Promise.resolve(foundHead);
};

export const mockAddDosingHead = (slot, chemical) => {
  const headIndex = mockDosingHeads.findIndex((h) => h.slot === slot);
  if (headIndex === -1) {
    return Promise.reject(new Error("Dosing head not found"));
  }
  mockDosingHeads[headIndex].chemical = chemical;
  mockDosingHeads[headIndex].status = "normal";
  return Promise.resolve({ message: `Chemical ${chemical} added to slot ${slot}` });
};

export const mockClearDosingHeadError = (slot) => {
  const headIndex = mockDosingHeads.findIndex((h) => h.slot === slot);
  if (headIndex === -1) {
    return Promise.reject(new Error("Dosing head not found"));
  }
  mockDosingHeads[headIndex].status = "normal";
  return Promise.resolve({ message: `Error cleared for slot ${slot}` });
};

export const mockGetConsumableRackSlots = () => {
  return Promise.resolve(mockConsumableRackSlots);
};

export const mockGetConsumableRackSlot = (level, row) => {
  const foundSlot = mockConsumableRackSlots.find(
    (s) => s.level === level && s.row === row
  );
  if (!foundSlot) {
    return Promise.reject(new Error("Slot not found"));
  }
  return Promise.resolve(foundSlot);
};

export const mockCleanConsumableRackSlot = (level, row) => {
  const slotIndex = mockConsumableRackSlots.findIndex(
    (s) => s.level === level && s.row === row
  );
  if (slotIndex === -1) {
    return Promise.reject(new Error("Slot not found"));
  }
  mockConsumableRackSlots[slotIndex].slot_status = "filled";
  mockConsumableRackSlots[slotIndex].sample_id = null;
  mockConsumableRackSlots[slotIndex].sample_name = null;
  mockConsumableRackSlots[slotIndex].consumable_status = {
    vial: "normal",
    cap: "normal"
  };
  return Promise.resolve({ message: `Slot level_${level}_row_${row} cleaned` });
};

export const mockCleanConsumableRackLevel = (level) => {
  const levelSlots = mockConsumableRackSlots.filter(s => s.level === level);
  if (levelSlots.length === 0) {
    return Promise.reject(new Error("Level not found"));
  }
  
  // Check if all slots in the level are in wait_for_removal status
  const allReadyForCleaning = levelSlots.every(s => s.slot_status === "wait_for_removal");
  if (!allReadyForCleaning) {
    return Promise.reject(new Error("Not all slots in level are ready for cleaning"));
  }
  
  // Clean all slots in the level
  mockConsumableRackSlots = mockConsumableRackSlots.map(slot => {
    if (slot.level === level) {
      return {
        ...slot,
        slot_status: "filled",
        sample_id: null,
        sample_name: null,
        consumable_status: {
          vial: "normal",
          cap: "normal"
        }
      };
    }
    return slot;
  });
  
  return Promise.resolve({ message: `Level ${level} cleaned` });
};

export const getXRDSampleHolderSlots = async () => {
  return mockXRDSampleHolderSlots;
};

export const getXRDSampleHolderSlot = async (slot) => {
  const foundSlot = mockXRDSampleHolderSlots.find(s => s.slot === slot);
  if (!foundSlot) throw new Error(`Slot ${slot} not found`);
  return foundSlot;
};

export const markXRDSampleHolderAsClean = async (slot) => {
  const slotData = mockXRDSampleHolderSlots.find(s => s.slot === slot);
  if (!slotData) {
    throw new Error(`Slot ${slot} not found`);
  }
  if (slotData.status !== 'loaded') {
    throw new Error(`Cannot mark slot ${slot} as clean. Current status: ${slotData.status}`);
  }
  
  mockXRDSampleHolderSlots = mockXRDSampleHolderSlots.map(s => 
    s.slot === slot ? { ...s, status: 'clean', sample_id: null } : s
  );
  return { message: `Slot ${slot} marked as clean` };
};

export const disableXRDSampleHolderSlot = async (slot) => {
  const slotData = mockXRDSampleHolderSlots.find(s => s.slot === slot);
  if (!slotData) {
    throw new Error(`Slot ${slot} not found`);
  }
  if (slotData.status !== 'clean') {
    throw new Error(`Cannot disable slot ${slot}. Current status: ${slotData.status}`);
  }
  
  mockXRDSampleHolderSlots = mockXRDSampleHolderSlots.map(s => 
    s.slot === slot ? { ...s, status: 'disabled' } : s
  );
  return { message: `Slot ${slot} disabled` };
};

export const enableXRDSampleHolderSlot = async (slot) => {
  const slotData = mockXRDSampleHolderSlots.find(s => s.slot === slot);
  if (!slotData) {
    throw new Error(`Slot ${slot} not found`);
  }
  if (slotData.status !== 'disabled') {
    throw new Error(`Cannot enable slot ${slot}. Current status: ${slotData.status}`);
  }
  
  mockXRDSampleHolderSlots = mockXRDSampleHolderSlots.map(s => 
    s.slot === slot ? { ...s, status: 'clean' } : s
  );
  return { message: `Slot ${slot} enabled` };
};

export const cleanXRDSampleHolderRow = async (row) => {
  const rowSlots = mockXRDSampleHolderSlots.filter(s => s.slot.startsWith(row));
  const errors = [];
  const cleanedSlots = [];

  for (const slot of rowSlots) {
    if (slot.status === 'loaded') {
      cleanedSlots.push(slot.slot);
    } else if (slot.status !== 'clean') {
      errors.push(`Cannot clean slot ${slot.slot}. Current status: ${slot.status}`);
    }
  }

  if (errors.length > 0) {
    throw new Error(errors.join('; '));
  }

  mockXRDSampleHolderSlots = mockXRDSampleHolderSlots.map(s => 
    cleanedSlots.includes(s.slot) ? { ...s, status: 'clean', sample_id: null } : s
  );

  return { message: `Cleaned slots in row ${row}: ${cleanedSlots.join(', ')}` };
};

export const disableXRDSampleHolderRow = async (row) => {
  const rowSlots = mockXRDSampleHolderSlots.filter(s => s.slot.startsWith(row));
  const errors = [];
  const disabledSlots = [];

  for (const slot of rowSlots) {
    if (slot.status === 'clean') {
      disabledSlots.push(slot.slot);
    } else if (slot.status !== 'disabled') {
      errors.push(`Cannot disable slot ${slot.slot}. Current status: ${slot.status}`);
    }
  }

  if (errors.length > 0) {
    throw new Error(errors.join('; '));
  }

  mockXRDSampleHolderSlots = mockXRDSampleHolderSlots.map(s => 
    disabledSlots.includes(s.slot) ? { ...s, status: 'disabled' } : s
  );

  return { message: `Disabled slots in row ${row}: ${disabledSlots.join(', ')}` };
};

export const enableXRDSampleHolderRow = async (row) => {
  const rowSlots = mockXRDSampleHolderSlots.filter(s => s.slot.startsWith(row));
  const errors = [];
  const enabledSlots = [];

  for (const slot of rowSlots) {
    if (slot.status === 'disabled') {
      enabledSlots.push(slot.slot);
    } else if (slot.status !== 'clean') {
      errors.push(`Cannot enable slot ${slot.slot}. Current status: ${slot.status}`);
    }
  }

  if (errors.length > 0) {
    throw new Error(errors.join('; '));
  }

  mockXRDSampleHolderSlots = mockXRDSampleHolderSlots.map(s => 
    enabledSlots.includes(s.slot) ? { ...s, status: 'clean' } : s
  );

  return { message: `Enabled slots in row ${row}: ${enabledSlots.join(', ')}` };
};

export const getDosingHeads = async () => {
  return mockDosingHeads;
};

export const getDosingHead = async (slot) => {
  const foundHead = mockDosingHeads.find(h => h.slot === slot);
  if (!foundHead) throw new Error(`Slot ${slot} not found`);
  return foundHead;
};

export const addDosingHead = async (slot, chemical) => {
  const foundHead = mockDosingHeads.find(h => h.slot === slot);
  if (!foundHead) throw new Error(`Slot ${slot} not found`);
  if (foundHead.chemical) throw new Error(`Dosing head ${slot} is already occupied by ${foundHead.chemical}.`);
  foundHead.chemical = chemical;
  foundHead.status = 'normal';
  return { message: `Dosing head with chemical ${chemical} added to slot ${slot}` };
};

export const clearDosingHeadError = async (slot) => {
  const foundHead = mockDosingHeads.find(h => h.slot === slot);
  if (!foundHead) throw new Error(`Slot ${slot} not found`);
  if (foundHead.status !== 'stuck' && foundHead.status !== 'empty') throw new Error(`Cannot clear error for slot ${slot}. Current status: ${foundHead.status}`);
  foundHead.status = 'normal';
  return { message: `Error cleared for slot ${slot}` };
};

export const getConsumableRackSlots = async () => {
  return mockConsumableRackSlots;
};

export const getConsumableRackSlot = async (level, row) => {
  const foundSlot = mockConsumableRackSlots.find(s => s.level === level && s.row === row);
  if (!foundSlot) throw new Error(`Slot level_${level}_row_${row} not found`);
  return foundSlot;
};

export const cleanConsumableRackSlot = async (level, row) => {
  const foundSlot = mockConsumableRackSlots.find(s => s.level === level && s.row === row);
  if (!foundSlot) throw new Error(`Slot level_${level}_row_${row} not found`);
  if (foundSlot.slot_status !== 'wait_for_removal') throw new Error(`Cannot clean slot level_${level}_row_${row}. Current status: ${foundSlot.slot_status}`);
  foundSlot.slot_status = 'filled';
  foundSlot.sample_id = null;
  Object.keys(foundSlot.consumable_status).forEach(type => {
    foundSlot.consumable_status[type] = 'available';
  });
  return { message: `Slot level_${level}_row_${row} cleaned` };
};

export const unloadDosingHead = async (slot) => {
  const foundHead = mockDosingHeads.find(h => h.slot === slot);
  if (!foundHead) throw new Error(`Slot ${slot} not found`);
  if (!foundHead.chemical) throw new Error(`Dosing head ${slot} is already empty`);
  if (foundHead.status !== 'normal') throw new Error(`Cannot unload dosing head ${slot}. Current status: ${foundHead.status}`);
  foundHead.chemical = null;
  return { message: `Dosing head unloaded from slot ${slot}` };
};

// Mock ionic conductivity functions - single measurement system
let currentMockMeasurement = null;

// Helper function to get mock sample names
const getMockSampleName = (sampleId) => {
  const sampleNames = {
    "507f1f77bcf86cd799439011": "Sample A",
    "507f1f77bcf86cd799439012": "Sample B", 
    "507f1f77bcf86cd799439013": "Sample C",
    "507f1f77bcf86cd799439014": "Sample D",
    "507f1f77bcf86cd799439015": "Sample E"
  };
  return sampleNames[sampleId] || `Sample ${sampleId.slice(-4)}`;
};

export const startIonicConductivityMeasurement = async (measurementData) => {
  // Check if there's already a measurement running
  if (currentMockMeasurement && currentMockMeasurement.status === "running") {
    throw {
      response: {
        status: 409,
        data: {
          detail: `A measurement is already running for sample ${currentMockMeasurement.sample_id}`
        }
      }
    };
  }

  // Validate ObjectId format (24 hex characters)
  const objectIdRegex = /^[0-9a-fA-F]{24}$/;
  if (!objectIdRegex.test(measurementData.sample_id)) {
    throw {
      response: {
        data: {
          detail: "Sample ID must be a valid ObjectId (24 hex characters)"
        }
      }
    };
  }

  // Mock some sample IDs that exist in the database
  const validSampleIds = [
    "507f1f77bcf86cd799439011",
    "507f1f77bcf86cd799439012", 
    "507f1f77bcf86cd799439013",
    "507f1f77bcf86cd799439014",
    "507f1f77bcf86cd799439015"
  ];

  if (!validSampleIds.includes(measurementData.sample_id)) {
    throw {
      response: {
        data: {
          detail: "Sample not found in the database."
        }
      }
    };
  }

  const createdAt = new Date().toISOString();
  
  // Create current measurement
  currentMockMeasurement = {
    sample_id: measurementData.sample_id,
    sample_name: getMockSampleName(measurementData.sample_id),
    sample_height: measurementData.sample_height || null,
    peis_params: measurementData.peis_params,
    include_electronic_conductivity: measurementData.include_electronic_conductivity || false,
    electronic_conductivity_params: measurementData.electronic_conductivity_params || null,
    status: "queued",
    message: "Measurement queued",
    created_at: createdAt,
    started_at: null,
    completed_at: null,
    error: null,
    progress: 0.0
  };

  // Simulate measurement progression
  setTimeout(() => {
    if (currentMockMeasurement) {
      currentMockMeasurement.status = "running";
      currentMockMeasurement.started_at = new Date().toISOString();
      currentMockMeasurement.progress = 0.1;
      currentMockMeasurement.message = "Starting measurement...";
    }
  }, 1000);

  setTimeout(() => {
    if (currentMockMeasurement) {
      currentMockMeasurement.progress = 0.3;
      currentMockMeasurement.message = "Connecting to device...";
    }
  }, 3000);

  setTimeout(() => {
    if (currentMockMeasurement) {
      currentMockMeasurement.progress = 0.5;
      currentMockMeasurement.message = "Running ionic conductivity measurement...";
    }
  }, 5000);

  // If electronic conductivity is included, add additional steps
  if (measurementData.include_electronic_conductivity) {
    setTimeout(() => {
      if (currentMockMeasurement) {
        currentMockMeasurement.progress = 0.7;
        currentMockMeasurement.message = "Running electronic conductivity measurement...";
      }
    }, 12000);

    setTimeout(() => {
      if (currentMockMeasurement) {
        currentMockMeasurement.progress = 0.9;
        currentMockMeasurement.message = "Saving results...";
      }
    }, 20000);

    setTimeout(() => {
      if (currentMockMeasurement) {
        currentMockMeasurement.status = "completed";
        currentMockMeasurement.progress = 1.0;
        currentMockMeasurement.message = "Measurement completed successfully: ionic conductivity, electronic conductivity";
        currentMockMeasurement.completed_at = new Date().toISOString();
      }
    }, 25000);
  } else {
    setTimeout(() => {
      if (currentMockMeasurement) {
        currentMockMeasurement.progress = 0.9;
        currentMockMeasurement.message = "Saving results...";
      }
    }, 15000);

    setTimeout(() => {
      if (currentMockMeasurement) {
        currentMockMeasurement.status = "completed";
        currentMockMeasurement.progress = 1.0;
        currentMockMeasurement.message = "Measurement completed successfully: ionic conductivity";
        currentMockMeasurement.completed_at = new Date().toISOString();
      }
    }, 20000);
  }

  return {
    sample_id: measurementData.sample_id,
    sample_height: measurementData.sample_height,
    peis_params: measurementData.peis_params,
    include_electronic_conductivity: measurementData.include_electronic_conductivity || false,
    electronic_conductivity_params: measurementData.electronic_conductivity_params || null,
    status: "queued",
    message: "Measurement started successfully"
  };
};

export const getMeasurementStatus = async () => {
  if (!currentMockMeasurement) {
    return {};
  }
  
  return currentMockMeasurement;
};

export const clearMeasurement = async () => {
  if (!currentMockMeasurement) {
    throw {
      response: {
        status: 404,
        data: {
          detail: "No measurement found"
        }
      }
    };
  }

  if (currentMockMeasurement.status === "running" || currentMockMeasurement.status === "queued") {
    throw {
      response: {
        status: 400,
        data: {
          detail: "Cannot clear a running measurement"
        }
      }
    };
  }

  currentMockMeasurement = null;
  return { message: "Measurement cleared successfully" };
};

export const getSampleMeasurements = async (sampleId) => {
  // Validate ObjectId format (24 hex characters)
  const objectIdRegex = /^[0-9a-fA-F]{24}$/;
  if (!objectIdRegex.test(sampleId)) {
    throw {
      response: {
        data: {
          detail: "Sample ID must be a valid ObjectId (24 hex characters)"
        }
      }
    };
  }

  // Mock some sample IDs that exist in the database
  const validSampleIds = [
    "507f1f77bcf86cd799439011",
    "507f1f77bcf86cd799439012", 
    "507f1f77bcf86cd799439013",
    "507f1f77bcf86cd799439014",
    "507f1f77bcf86cd799439015"
  ];

  if (!validSampleIds.includes(sampleId)) {
    throw {
      response: {
        data: {
          detail: "Sample not found in the database."
        }
      }
    };
  }

  // Mock some samples having existing ionic conductivity data
  const samplesWithIonicData = [
    "507f1f77bcf86cd799439012",
    "507f1f77bcf86cd799439014"
  ];

  // Mock some samples having existing electronic conductivity data
  const samplesWithElectronicData = [
    "507f1f77bcf86cd799439014" // Sample 014 has both ionic and electronic data
  ];

  const hasIonicData = samplesWithIonicData.includes(sampleId);
  const hasElectronicData = samplesWithElectronicData.includes(sampleId);

  const response = {
    sample_id: sampleId,
    ionic_conductivity_measurements: [],
    electronic_conductivity_measurements: []
  };

  if (hasIonicData) {
    // Create mock ionic measurements - some samples have multiple measurements
    const ionicMeasurements = [];
    
    if (sampleId === "507f1f77bcf86cd799439014") {
      // Sample 014 has multiple ionic measurements
      ionicMeasurements.push({
        measurement_id: "meas_20240101_120000_001234",
        timestamp: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(), // 5 days ago
        filename: `ionic_conductivity_${sampleId}_meas_20240101_120000_001234_192.168.1.33.csv`,
        sample_height_mm: 4.8,
        sample_diameter_mm: 6.5024,
        data: {}, // Would contain actual measurement data
        peis_params: {
          initial_frequency: 70000000,
          final_frequency: 0.007,
          frequency_number: 6,
          repeat: 0
        }
      });
      
      ionicMeasurements.push({
        measurement_id: "meas_20240103_140000_005678",
        timestamp: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(), // 3 days ago
        filename: `ionic_conductivity_${sampleId}_meas_20240103_140000_005678_192.168.1.33.csv`,
        sample_height_mm: 5.2,
        sample_diameter_mm: 6.5024,
        data: {}, // Would contain actual measurement data
        peis_params: {
          initial_frequency: 70000000,
          final_frequency: 0.007,
          frequency_number: 6,
          repeat: 0
        }
      });
    } else {
      // Other samples have single ionic measurement
      ionicMeasurements.push({
        measurement_id: "meas_20240102_100000_002345",
        timestamp: new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString(), // 4 days ago
        filename: `ionic_conductivity_${sampleId}_meas_20240102_100000_002345_192.168.1.33.csv`,
        sample_height_mm: 5.0,
        sample_diameter_mm: 6.5024,
        data: {}, // Would contain actual measurement data
        peis_params: {
          initial_frequency: 70000000,
          final_frequency: 0.007,
          frequency_number: 6,
          repeat: 0
        }
      });
    }
    
    response.ionic_conductivity_measurements = ionicMeasurements;
  }

  if (hasElectronicData) {
    // Create mock electronic measurements
    const electronicMeasurements = [];
    
    if (sampleId === "507f1f77bcf86cd799439014") {
      // Sample 014 has electronic measurements
      electronicMeasurements.push({
        measurement_id: "meas_20240103_150000_006789",
        timestamp: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(), // 2 days ago
        filename: `electronic_conductivity_${sampleId}_meas_20240103_150000_006789_192.168.1.33.csv`,
        sample_height_mm: 5.2,
        sample_diameter_mm: 6.5024,
        data: {}, // Would contain actual measurement data
        electronic_params: {
          voltages: [0.5],
          durations: [600]
        }
      });
    }
    
    response.electronic_conductivity_measurements = electronicMeasurements;
  }

  return response;
};

export const getIonicConductivityPlotData = async (sampleId, measurementId = null) => {
  // Validate ObjectId format (24 hex characters)
  const objectIdRegex = /^[0-9a-fA-F]{24}$/;
  if (!objectIdRegex.test(sampleId)) {
    throw {
      response: {
        data: {
          detail: "Sample ID must be a valid ObjectId (24 hex characters)"
        }
      }
    };
  }

  // Mock some sample IDs that exist in the database
  const validSampleIds = [
    "507f1f77bcf86cd799439011",
    "507f1f77bcf86cd799439012", 
    "507f1f77bcf86cd799439013",
    "507f1f77bcf86cd799439014",
    "507f1f77bcf86cd799439015"
  ];

  if (!validSampleIds.includes(sampleId)) {
    throw {
      response: {
        data: {
          detail: "Sample not found in the database."
        }
      }
    };
  }

  // Only samples with existing data have plot data
  const samplesWithPlotData = [
    "507f1f77bcf86cd799439012",
    "507f1f77bcf86cd799439014"
  ];

  if (!samplesWithPlotData.includes(sampleId)) {
    throw {
      response: {
        status: 404,
        data: {
          detail: "No ionic conductivity data found for this sample"
        }
      }
    };
  }

  // If specific measurement ID is provided, validate it exists
  if (measurementId) {
    const validMeasurementIds = [
      "meas_20240101_120000_001234",
      "meas_20240103_140000_005678",
      "meas_20240102_100000_002345",
      "legacy_ionic"
    ];
    
    if (!validMeasurementIds.includes(measurementId)) {
      throw {
        response: {
          status: 404,
          data: {
            detail: "Ionic conductivity measurement not found"
          }
        }
      };
    }
  }

  return new Promise((resolve) => {
    setTimeout(() => {
      // Generate mock Nyquist plot data in Plotly JSON format
      const frequencies = Array.from({length: 50}, (_, i) => Math.pow(10, 0.1 * i - 2));
      const real_parts = [];
      const imag_parts = [];
      const log_frequencies = [];
      
      // Vary the plot slightly based on measurement ID to show different data
      const measurementVariation = measurementId === "meas_20240103_140000_005678" ? 1.2 : 1.0;
      
      frequencies.forEach(freq => {
        // Simple semicircle model for Nyquist plot
        const omega = 2 * Math.PI * freq;
        const R_s = 10 * measurementVariation; // Series resistance
        const R_p = 100 * measurementVariation; // Parallel resistance  
        const C = 1e-9; // Capacitance
        const tau = R_p * C;
        
        const real = R_s + R_p / (1 + Math.pow(omega * tau, 2));
        const imag = -R_p * omega * tau / (1 + Math.pow(omega * tau, 2));
        
        real_parts.push(real);
        imag_parts.push(imag);
        log_frequencies.push(Math.log10(freq));
      });

      const plotData = {
        data: [
          {
            x: real_parts,
            y: imag_parts,
            mode: 'markers',
            type: 'scatter',
            marker: {
              size: 8,
              color: log_frequencies,
              colorscale: 'Viridis',
              colorbar: {
                title: 'log₁₀(Frequency [Hz])',
                titleside: 'right'
              },
              showscale: true
            },
            text: frequencies.map(freq => `Freq: ${freq.toExponential(2)} Hz`),
            hovertemplate: 'ReIm: %{x:.2f} Ω<br>ImRe: %{y:.2f} Ω<br>%{text}<extra></extra>',
            name: 'Impedance Data'
          }
        ],
        layout: {
          title: {
            text: `Nyquist Plot - Ionic Conductivity${measurementId ? ` (${measurementId})` : ''}`,
            x: 0.5
          },
          xaxis: {
            title: 'ReIm (Ω)',
            showgrid: true,
            zeroline: true
          },
          yaxis: {
            title: 'ImRe (Ω)',
            showgrid: true,
            zeroline: true
          },
          hovermode: 'closest',
          showlegend: false,
          plot_bgcolor: 'white',
          paper_bgcolor: 'white'
        }
      };

      resolve(plotData);
    }, 1000);
  });
};

export const getElectronicConductivityPlotData = async (sampleId, measurementId = null) => {
  // Validate ObjectId format (24 hex characters)
  const objectIdRegex = /^[0-9a-fA-F]{24}$/;
  if (!objectIdRegex.test(sampleId)) {
    throw {
      response: {
        data: {
          detail: "Sample ID must be a valid ObjectId (24 hex characters)"
        }
      }
    };
  }

  // Mock some sample IDs that exist in the database
  const validSampleIds = [
    "507f1f77bcf86cd799439011",
    "507f1f77bcf86cd799439012", 
    "507f1f77bcf86cd799439013",
    "507f1f77bcf86cd799439014",
    "507f1f77bcf86cd799439015"
  ];

  if (!validSampleIds.includes(sampleId)) {
    throw {
      response: {
        data: {
          detail: "Sample not found in the database."
        }
      }
    };
  }

  // Only some samples have electronic conductivity data (fewer than ionic)
  const samplesWithElectronicData = [
    "507f1f77bcf86cd799439014"  // Only one sample for now
  ];

  if (!samplesWithElectronicData.includes(sampleId)) {
    throw {
      response: {
        status: 404,
        data: {
          detail: "No electronic conductivity data found for this sample"
        }
      }
    };
  }

  // If specific measurement ID is provided, validate it exists
  if (measurementId) {
    const validMeasurementIds = [
      "meas_20240103_150000_006789",
      "legacy_electronic"
    ];
    
    if (!validMeasurementIds.includes(measurementId)) {
      throw {
        response: {
          status: 404,
          data: {
            detail: "Electronic conductivity measurement not found"
          }
        }
      };
    }
  }

  return new Promise((resolve) => {
    setTimeout(() => {
      // Generate mock I-V curve data for electronic conductivity
      const voltages = [];
      const currents = [];
      const conductivity = [];
      
      // Create voltage sweep from -2V to +2V
      for (let i = 0; i <= 40; i++) {
        const voltage = -2 + (i * 4 / 40); // -2V to +2V
        voltages.push(voltage);
        
        // Mock current response with some non-linearity and noise
        const resistance = 1000 + Math.abs(voltage) * 500; // Variable resistance
        const current = voltage / resistance * 1000; // Convert to mA
        const noise = (Math.random() - 0.5) * 0.01; // Small random noise
        currents.push(current + noise);
        
        // Calculate conductivity (S/cm) - mock values
        const cond = Math.abs(current / voltage) * 0.1 || 0; // Avoid division by zero at V=0
        conductivity.push(cond);
      }

      const plotData = {
        data: [
          {
            x: voltages,
            y: currents,
            mode: 'lines+markers',
            type: 'scatter',
            marker: {
              size: 6,
              color: '#e74c3c'
            },
            line: {
              color: '#e74c3c',
              width: 2
            },
            name: 'I-V Curve',
            hovertemplate: 'Voltage: %{x:.3f} V<br>Current: %{y:.3f} mA<extra></extra>'
          }
        ],
        layout: {
          title: {
            text: `Electronic Conductivity - I-V Curve${measurementId ? ` (${measurementId})` : ''}`,
            x: 0.5
          },
          xaxis: {
            title: 'Voltage (V)',
            showgrid: true,
            zeroline: true
          },
          yaxis: {
            title: 'Current (mA)',
            showgrid: true,
            zeroline: true
          },
          hovermode: 'closest',
          showlegend: false,
          plot_bgcolor: 'white',
          paper_bgcolor: 'white'
        }
      };

      resolve(plotData);
    }, 800); // Slightly faster than ionic data loading
  });
};

export const getDefaultMeasurementParameters = async () => {
  // Return the same default values as defined in biologic.py
  return {
    peis_params: {
      initial_frequency: 70000000, // 7e7
      final_frequency: 0.007,      // 7e-3
      frequency_number: 6,
      repeat: 0
    },
    electronic_conductivity_params: {
      voltages: [0.5],  // From DEFAULT_CA_PARAMS
      durations: [600]  // From DEFAULT_CA_PARAMS (10 minutes)
    }
  };
};

export const updateSampleHeight = async (sampleHeight) => {
  if (!currentMockMeasurement) {
    throw {
      response: {
        status: 404,
        data: {
          detail: "No active measurement found"
        }
      }
    };
  }

  if (currentMockMeasurement.status === "running") {
    throw {
      response: {
        status: 400,
        data: {
          detail: "Cannot update sample height while measurement is running"
        }
      }
    };
  }

  if (sampleHeight <= 0) {
    throw {
      response: {
        status: 400,
        data: {
          detail: "Sample height must be positive"
        }
      }
    };
  }

  // Update the sample height
  currentMockMeasurement.sample_height = sampleHeight;

  // Log successful database update (simulated)
  console.log(`Mock: Successfully updated sample height in database for sample ${currentMockMeasurement.sample_id}`);

  return currentMockMeasurement;
};

export const loadSample = async (sampleId, ionicMeasurementId = null, electronicMeasurementId = null) => {
  // Validate ObjectId format (24 hex characters)
  const objectIdRegex = /^[0-9a-fA-F]{24}$/;
  if (!objectIdRegex.test(sampleId)) {
    throw {
      response: {
        status: 400,
        data: {
          detail: "Sample ID must be a valid ObjectId (24 hex characters)"
        }
      }
    };
  }

  // Mock some sample IDs that exist in the database
  const validSampleIds = [
    "507f1f77bcf86cd799439011",
    "507f1f77bcf86cd799439012", 
    "507f1f77bcf86cd799439013",
    "507f1f77bcf86cd799439014",
    "507f1f77bcf86cd799439015"
  ];

  if (!validSampleIds.includes(sampleId)) {
    throw {
      response: {
        status: 400,
        data: {
          detail: "Sample not found in the database."
        }
      }
    };
  }

  // Get all measurements for this sample first
  const measurementsResponse = await getSampleMeasurements(sampleId);
  
  if (!measurementsResponse.ionic_conductivity_measurements?.length && 
      !measurementsResponse.electronic_conductivity_measurements?.length) {
    throw {
      response: {
        status: 404,
        data: {
          detail: "No conductivity data found for this sample"
        }
      }
    };
  }

  // Find specific measurements or use latest ones
  let ionicMeasurement = null;
  let electronicMeasurement = null;
  
  if (ionicMeasurementId) {
    ionicMeasurement = measurementsResponse.ionic_conductivity_measurements.find(
      m => m.measurement_id === ionicMeasurementId
    );
    if (!ionicMeasurement) {
      throw {
        response: {
          status: 404,
          data: {
            detail: "Specified ionic measurement not found"
          }
        }
      };
    }
  } else if (measurementsResponse.ionic_conductivity_measurements?.length > 0) {
    // Use latest ionic measurement
    ionicMeasurement = measurementsResponse.ionic_conductivity_measurements[
      measurementsResponse.ionic_conductivity_measurements.length - 1
    ];
  }
  
  if (electronicMeasurementId) {
    electronicMeasurement = measurementsResponse.electronic_conductivity_measurements.find(
      m => m.measurement_id === electronicMeasurementId
    );
    if (!electronicMeasurement) {
      throw {
        response: {
          status: 404,
          data: {
            detail: "Specified electronic measurement not found"
          }
        }
      };
    }
  } else if (measurementsResponse.electronic_conductivity_measurements?.length > 0) {
    // Use latest electronic measurement
    electronicMeasurement = measurementsResponse.electronic_conductivity_measurements[
      measurementsResponse.electronic_conductivity_measurements.length - 1
    ];
  }

  // Determine sample height and parameters from the selected measurements
  let sampleHeight = null;
  let peis_params = null;
  let electronic_params = null;
  
  if (ionicMeasurement) {
    sampleHeight = ionicMeasurement.sample_height_mm;
    peis_params = ionicMeasurement.peis_params;
  }
  
  if (electronicMeasurement) {
    if (sampleHeight === null) {
      sampleHeight = electronicMeasurement.sample_height_mm;
    }
    electronic_params = electronicMeasurement.electronic_params;
  }

  // Use default PEIS params if not available
  if (!peis_params) {
    peis_params = {
      initial_frequency: 70000000,
      final_frequency: 0.007,
      frequency_number: 6,
      repeat: 0
    };
  }

  // Determine measurement types message
  const measurementTypes = [];
  if (ionicMeasurement) measurementTypes.push("ionic conductivity");
  if (electronicMeasurement) measurementTypes.push("electronic conductivity");

  // Create a mock loaded measurement
  const loadedMeasurement = {
    sample_id: sampleId,
    sample_name: getMockSampleName(sampleId),
    sample_height: sampleHeight,
    peis_params: peis_params,
    include_electronic_conductivity: electronicMeasurement !== null,
    electronic_conductivity_params: electronic_params,
    status: "completed",
    message: `Loaded existing measurement: ${measurementTypes.join(', ')}`,
    created_at: new Date().toISOString(),
    started_at: new Date().toISOString(),
    completed_at: new Date().toISOString(),
    error: null,
    progress: 1.0,
    loaded_ionic_measurement_id: ionicMeasurement?.measurement_id || null,
    loaded_electronic_measurement_id: electronicMeasurement?.measurement_id || null
  };

  // Set this as the current measurement
  currentMockMeasurement = loadedMeasurement;

  return loadedMeasurement;
};

// Mock XRD measurement progress tracking
let mockXRDMeasurementProgress = {
  is_running: false,
  row: null,
  progress: 0,
  current_slot: null,
  total_slots: 0,
  status: "idle",
  completed_at: null,
  success: null
};

export const runXRDMeasurement = async (row) => {
  if (mockXRDMeasurementProgress.is_running) {
    throw {
      response: {
        status: 400,
        data: {
          detail: "A measurement is already running."
        }
      }
    };
  }

  // Check if row has samples
  const rowSlots = mockXRDSampleHolderSlots.filter(s => s.slot.startsWith(row));
  const samplesInRow = rowSlots.filter(s => s.sample_id !== null);

  if (samplesInRow.length === 0) {
    throw {
      response: {
        status: 400,
        data: {
          detail: `No samples found in row ${row}.`
        }
      }
    };
  }

  // Check that all slots are in acceptable states (not being used)
  const acceptableStates = ['loaded', 'clean', 'disabled'];
  const slotsInUse = rowSlots.filter(s => !acceptableStates.includes(s.status));

  if (slotsInUse.length > 0) {
    throw {
      response: {
        status: 400,
        data: {
          detail: `Cannot start measurement. Slots ${slotsInUse.map(s => s.slot).join(', ')} in row ${row} are currently being used.`
        }
      }
    };
  }

  // Initialize measurement
  mockXRDMeasurementProgress = {
    is_running: true,
    row: row,
    progress: 0,
    current_slot: null,
    total_slots: samplesInRow.length,
    status: "Starting measurement"
  };

  // Simulate measurement progression
  let currentSlotIndex = 0;
  const progressInterval = setInterval(() => {
    // Small chance of mid-measurement failure for testing
    const midMeasurementFailure = Math.random() < 0.05; // 5% chance per interval
    
    if (midMeasurementFailure && currentSlotIndex > 0) {
      // Simulate failure during measurement
      mockXRDMeasurementProgress.progress = Math.floor((currentSlotIndex / samplesInRow.length) * 100);
      mockXRDMeasurementProgress.is_running = false;
      mockXRDMeasurementProgress.completed_at = new Date().toISOString();
      mockXRDMeasurementProgress.status = "Error: Measurement interrupted - device communication lost";
      mockXRDMeasurementProgress.success = false;
      clearInterval(progressInterval);
    } else if (currentSlotIndex < samplesInRow.length) {
      const currentSlot = samplesInRow[currentSlotIndex];
      mockXRDMeasurementProgress.current_slot = currentSlot.slot;
      mockXRDMeasurementProgress.progress = Math.floor((currentSlotIndex / samplesInRow.length) * 100);
      mockXRDMeasurementProgress.status = `Measuring ${currentSlot.slot}`;
      
      currentSlotIndex++;
    } else {
      // Measurement complete - simulate occasional failures for testing
      const simulateFailure = Math.random() < 0.2; // 20% chance of failure for testing
      
      mockXRDMeasurementProgress.progress = 100;
      mockXRDMeasurementProgress.is_running = false;
      mockXRDMeasurementProgress.completed_at = new Date().toISOString();
      
      if (simulateFailure) {
        mockXRDMeasurementProgress.status = "Error: Aeris connection failed";
        mockXRDMeasurementProgress.success = false;
      } else {
        mockXRDMeasurementProgress.status = "Completed successfully";
        mockXRDMeasurementProgress.success = true;
      }
      
      clearInterval(progressInterval);
    }
  }, 3000); // Progress every 3 seconds

  return { message: `Started XRD measurement for row ${row} with ${samplesInRow.length} samples` };
};

export const getXRDMeasurementProgress = async () => {
  return mockXRDMeasurementProgress;
};
