import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Container,
  Box,
  Typography,
  TextField,
  Button,
  Grid,
  Link as MuiLink,
  Alert,
  CircularProgress
} from '@mui/material';
// import PersonAddOutlinedIcon from '@mui/icons-material/PersonAddOutlined'; // No longer used
import { styled } from '@mui/material/styles';

// TypeScript interfaces
interface RegistrationData {
  username: string;
  email: string;
  password: string;
  passwordConfirm: string;
  first_name?: string;
  last_name?: string;
}

interface ValidationErrors {
  username?: string;
  email?: string;
  password?: string;
  passwordConfirm?: string;
  first_name?: string;
  last_name?: string;
}

// Styled components
const StyledContainer = styled(Container)(({ theme }) => ({
  marginTop: theme.spacing(8),
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
}));

// const StyledAvatar = styled(Box)(({ theme }) => ({ // No longer used
//   margin: theme.spacing(1),
//   backgroundColor: theme.palette.secondary.main,
//   padding: theme.spacing(1.5),
//   borderRadius: '50%',
//   display: 'flex',
//   justifyContent: 'center',
//   alignItems: 'center',
// }));

const StyledForm = styled('form')(({ theme }) => ({
  width: '100%',
  marginTop: theme.spacing(1),
}));

const SubmitButton = styled(Button)(({ theme }) => ({
  margin: theme.spacing(3, 0, 2),
}));

const Register = () => {
  const [formData, setFormData] = useState<RegistrationData>({
    username: '',
    email: '',
    password: '',
    passwordConfirm: '',
    first_name: '',
    last_name: ''
  });
  
  const [validationErrors, setValidationErrors] = useState<ValidationErrors>({});
  const { register, loading, error } = useAuth();
  const navigate = useNavigate();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    
    if (validationErrors[name as keyof ValidationErrors]) {
      setValidationErrors(prev => ({ ...prev, [name as keyof ValidationErrors]: undefined }));
    }
  };

  const validateForm = (): boolean => {
    const errors: ValidationErrors = {};
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    
    if (!formData.username.trim()) {
      errors.username = 'Username is required';
    } else if (formData.username.length < 3) {
      errors.username = 'Username must be at least 3 characters';
    }
    
    if (!formData.email) {
      errors.email = 'Email is required';
    } else if (!emailRegex.test(formData.email)) {
      errors.email = 'Invalid email format';
    }
    
    if (!formData.password) {
      errors.password = 'Password is required';
    } else if (formData.password.length < 8) {
      errors.password = 'Password must be at least 8 characters';
    }
    
    if (formData.password !== formData.passwordConfirm) {
      errors.passwordConfirm = 'Passwords do not match';
    }
    
    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateForm()) return;
    
    const success = await register({
      username: formData.username,
      email: formData.email,
      password: formData.password,
      first_name: formData.first_name,
      last_name: formData.last_name
    });
    
    if (success) {
      navigate('/dashboard');
    }
  };

  return (
    <StyledContainer maxWidth="sm">
      {/* Replacing StyledAvatar with the logo */}
      <Box
        component="img"
        sx={{
          height: 80, // Adjust as needed, same as Login page for consistency
          mb: 2, // Margin bottom
        }}
        alt="MauZenfan Logo"
        src="/MauZenfan.mu.jpg" // Path relative to the public folder
      />
      
      <Typography component="h1" variant="h5">
        Create a SafeKids Account
      </Typography>
      
      <StyledForm onSubmit={handleSubmit} noValidate>
        {error && (
          <Alert severity="error" sx={{ mt: 2, mb: 2 }}>
            {error}
          </Alert>
        )}
        
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} component="div">
            <TextField
              autoComplete="given-name"
              name="first_name"
              fullWidth
              id="first_name"
              label="First Name"
              value={formData.first_name}
              onChange={handleChange}
              error={!!validationErrors.first_name}
              helperText={validationErrors.first_name}
              disabled={loading}
            />
          </Grid>
          <Grid item xs={12} sm={6} component="div">
            <TextField
              fullWidth
              id="last_name"
              label="Last Name"
              name="last_name"
              autoComplete="family-name"
              value={formData.last_name}
              onChange={handleChange}
              error={!!validationErrors.last_name}
              helperText={validationErrors.last_name}
              disabled={loading}
            />
          </Grid>
          <Grid item xs={12} component="div">
            <TextField
              required
              fullWidth
              id="username"
              label="Username"
              name="username"
              autoComplete="username"
              value={formData.username}
              onChange={handleChange}
              error={!!validationErrors.username}
              helperText={validationErrors.username}
              disabled={loading}
            />
          </Grid>
          <Grid item xs={12} component="div">
            <TextField
              required
              fullWidth
              id="email"
              label="Email Address"
              name="email"
              autoComplete="email"
              value={formData.email}
              onChange={handleChange}
              error={!!validationErrors.email}
              helperText={validationErrors.email}
              disabled={loading}
            />
          </Grid>
          <Grid item xs={12} sm={6} component="div">
            <TextField
              required
              fullWidth
              name="password"
              label="Password"
              type="password"
              id="password"
              autoComplete="new-password"
              value={formData.password}
              onChange={handleChange}
              error={!!validationErrors.password}
              helperText={validationErrors.password}
              disabled={loading}
            />
          </Grid>
          <Grid item xs={12} sm={6} component="div">
            <TextField
              required
              fullWidth
              name="passwordConfirm"
              label="Confirm Password"
              type="password"
              id="passwordConfirm"
              value={formData.passwordConfirm}
              onChange={handleChange}
              error={!!validationErrors.passwordConfirm}
              helperText={validationErrors.passwordConfirm}
              disabled={loading}
            />
          </Grid>
        </Grid>
        
        <SubmitButton
          type="submit"
          fullWidth
          variant="contained"
          color="primary"
          disabled={loading}
          sx={{ mt: 3 }}
        >
          {loading ? (
            <CircularProgress size={24} color="inherit" />
          ) : (
            'Sign Up'
          )}
        </SubmitButton>
        
        <Grid container justifyContent="flex-end">
          <Grid item component="div">
            <MuiLink 
              component={Link} 
              to="/login" 
              variant="body2"
              sx={{ cursor: 'pointer' }}
            >
              Already have an account? Sign in
            </MuiLink>
          </Grid>
        </Grid>
      </StyledForm>
    </StyledContainer>
  );
};

export default Register;