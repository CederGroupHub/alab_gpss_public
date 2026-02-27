# ALAB GPSS Control Panel

This is a user interface for managing the XRD sample holder rack, dosing head rack, and consumable rack in the ALAB GPSS system.

## Features

- View and manage XRD sample holders
- View and manage dosing heads
- View and manage consumable rack slots
- Update status of various components

## Project Structure

- `backend/`: FastAPI backend
  - `app.py`: Main FastAPI application
  - `routers/`: API routers for each device
  - `server.py`: Server script to run the FastAPI application
- `ui/`: React frontend
  - `src/`: Source code
    - `api/`: API service for the frontend
    - `components/`: React components
    - `pages/`: Page components

## Requirements

### Backend

- Python 3.8+
- FastAPI
- Uvicorn
- alab_management

### Frontend

- Node.js 14+
- npm or yarn

## Installation

### Backend

1. Install the required Python packages:

```bash
pip install fastapi uvicorn
```

2. Run the backend server:

```bash
cd alab-gpss/src/alab_gpss
python -m alab_gpss.backend.server
```

The backend server will be running at http://localhost:8000.

### Frontend

1. Install the required Node.js packages:

```bash
cd alab-gpss/src/alab_gpss/ui
npm install
```

2. Run the frontend development server:

```bash
npm start
```

The frontend will be running at http://localhost:3000.

## Usage

1. Open your browser and navigate to http://localhost:3000.
2. Use the navigation bar to switch between different devices.
3. For each device, you can:
   - View the status of all slots
   - Update the status of slots
   - Perform specific actions based on the device type

## API Documentation

The API documentation is available at http://localhost:8000/docs when the backend server is running.

## Testing the Frontend Without the Backend

The frontend can be tested without the backend by using the mock API functionality. This is useful for development and testing the UI independently of the backend.

### Using the Mock API

1. The mock API is enabled by default through the `.env` file in the `ui` directory.

2. To disable the mock API and use the real backend, set `REACT_APP_USE_MOCK_API=false` in the `.env` file.

3. The mock API provides simulated data for all the endpoints, allowing you to test the UI functionality without the backend running.

### Mock Data

The mock data includes:

- XRD sample holder slots with various statuses (clean, loaded, in_use, disabled)
- Dosing heads with different chemicals and statuses (normal, stuck, empty, in_use)
- Consumable rack slots organized by level and row, with different statuses and consumable types 