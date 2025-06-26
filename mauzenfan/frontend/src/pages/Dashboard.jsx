import React from 'react';
import { Box, Container, Typography, AppBar, Toolbar, Button } from '@mui/material';
import { useAuth } from '../context/AuthContext.tsx'; // Assuming useAuth might have a logout function
import { useNavigate } from 'react-router-dom';

const Dashboard = () => {
  const { logout } = useAuth(); // Or however logout is implemented
  const navigate = useNavigate();

  const handleLogout = async () => {
    // Assuming logout() is an async function that clears auth state and potentially redirects
    // If logout doesn't redirect, navigate to login page
    await logout();
    navigate('/login');
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Dashboard
          </Typography>
          <Button color="inherit" onClick={handleLogout}>
            Logout
          </Button>
        </Toolbar>
      </AppBar>
      <Container component="main" sx={{ mt: 4, mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Welcome to Your Dashboard
        </Typography>
        <Typography variant="body1">
          This is where your main application content will go.
          You can add more components, grids, cards, and other Material UI elements here
          to build out the features of your dashboard.
        </Typography>
        {/* Example of how you might link to other sections if they existed */}
        {/* <Box sx={{ mt: 2 }}>
          <Button variant="contained" sx={{ mr: 1 }} onClick={() => navigate('/child-tracker')}>Child Tracker</Button>
          <Button variant="contained" sx={{ mr: 1 }} onClick={() => navigate('/safe-zones')}>Safe Zones</Button>
          <Button variant="contained" onClick={() => navigate('/alerts')}>Alerts</Button>
        </Box> */}
      </Container>
      <Box component="footer" sx={{ py: 3, px: 2, mt: 'auto', backgroundColor: (theme) =>
          theme.palette.mode === 'light' ? theme.palette.grey[200] : theme.palette.grey[800],
        }}
      >
        <Container maxWidth="sm">
          <Typography variant="body2" color="text.secondary" align="center">
            {'© '}
            Mauzenfan {new Date().getFullYear()}
            {'.'}
          </Typography>
        </Container>
      </Box>
    </Box>
  );
};

export default Dashboard;
