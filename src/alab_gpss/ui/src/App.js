import React from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Box from '@mui/material/Box';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Container from '@mui/material/Container';
import Link from '@mui/material/Link';
import { Link as RouterLink } from 'react-router-dom';

import XRDSampleHolderPage from './pages/XRDSampleHolderPage';
import DosingHeadPage from './pages/DosingHeadPage';
import ConsumableRackPage from './pages/ConsumableRackPage';
import IonicConductivityPage from './pages/IonicConductivityPage';

// Create a theme
const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
  },
});

// Navigation component with active link highlighting
const Navigation = () => {
  const location = useLocation();
  
  return (
    <>
      <Link 
        component={RouterLink} 
        to="/" 
        color="inherit" 
        sx={{ 
          mx: 1, 
          textDecoration: 'none',
          fontWeight: location.pathname === '/' ? 'bold' : 'normal'
        }}
      >
        Consumable Rack
      </Link>
      <Link 
        component={RouterLink} 
        to="/dosing-head" 
        color="inherit" 
        sx={{ 
          mx: 1, 
          textDecoration: 'none',
          fontWeight: location.pathname === '/dosing-head' ? 'bold' : 'normal'
        }}
      >
        Dosing Head
      </Link>
      <Link 
        component={RouterLink} 
        to="/xrd-sample-holder" 
        color="inherit" 
        sx={{ 
          mx: 1, 
          textDecoration: 'none',
          fontWeight: location.pathname === '/xrd-sample-holder' ? 'bold' : 'normal'
        }}
      >
        XRD Sample Holder
      </Link>
      <Link 
        component={RouterLink} 
        to="/ionic-conductivity" 
        color="inherit" 
        sx={{ 
          mx: 1, 
          textDecoration: 'none',
          fontWeight: location.pathname === '/ionic-conductivity' ? 'bold' : 'normal'
        }}
      >
        Ionic Conductivity
      </Link>
    </>
  );
};

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Router>
        <Box sx={{ flexGrow: 1 }}>
          <AppBar position="static">
            <Toolbar>
              <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
                ALAB GPSS Control Panel
              </Typography>
              <Navigation />
            </Toolbar>
          </AppBar>
          <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
            <Routes>
              <Route path="/" element={<ConsumableRackPage />} />
              <Route path="/dosing-head" element={<DosingHeadPage />} />
              <Route path="/xrd-sample-holder" element={<XRDSampleHolderPage />} />
              <Route path="/ionic-conductivity" element={<IonicConductivityPage />} />
            </Routes>
          </Container>
        </Box>
      </Router>
    </ThemeProvider>
  );
}

export default App; 