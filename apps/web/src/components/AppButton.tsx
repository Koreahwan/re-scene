import React from 'react';

export interface AppButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'solid' | 'subtle' | 'outline' | 'ghost' | 'danger';
  size?: 'lg' | 'md' | 'sm' | 'xs';
  icon?: React.ReactNode;
  iconPosition?: 'left' | 'right';
  isLoading?: boolean;
  fullWidth?: boolean;
}

export const AppButton: React.FC<AppButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  icon,
  iconPosition = 'left',
  isLoading = false,
  fullWidth = false,
  style,
  disabled,
  ...rest
}) => {
  const sizeStyles = {
    lg: { padding: '16px 24px', fontSize: '17px', height: '58px', radius: '8px', gap: '8px' },
    md: { padding: '12px 20px', fontSize: '15px', height: '48px', radius: '8px', gap: '8px' },
    sm: { padding: '8px 16px', fontSize: '13px', height: '36px', radius: '6px', gap: '6px' },
    xs: { padding: '4px 10px', fontSize: '12px', height: '28px', radius: '4px', gap: '4px' },
  }[size];

  const variantStyles = {
    primary: {
      background: '#4C22F4',
      color: '#FFFFFF',
      border: 'none',
      boxShadow: '0 2px 8px #4C22F430',
    },
    solid: {
      background: '#4C22F4',
      color: '#FFFFFF',
      border: 'none',
      boxShadow: '0 2px 8px #4C22F430',
    },
    secondary: {
      background: '#F0EDFF',
      color: '#4C22F4',
      border: '1px solid #4C22F430',
      boxShadow: 'none',
    },
    subtle: {
      background: '#F0EDFF',
      color: '#4C22F4',
      border: '1px solid #4C22F430',
      boxShadow: 'none',
    },
    outline: {
      background: 'transparent',
      color: '#4C22F4',
      border: '1px solid #4C22F4',
    },
    ghost: {
      background: 'transparent',
      color: '#2D2D34',
      border: '1px solid transparent',
    },
    danger: {
      background: '#EB5757',
      color: '#FFFFFF',
      border: 'none',
    }
  }[variant];

  return (
    <button
      disabled={disabled || isLoading}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'inherit',
        gap: sizeStyles.gap,
        padding: sizeStyles.padding,
        fontSize: sizeStyles.fontSize,
        fontWeight: 600,
        borderRadius: sizeStyles.radius,
        width: fullWidth ? '100%' : 'auto',
        height: sizeStyles.height,
        cursor: disabled || isLoading ? 'not-allowed' : 'pointer',
        opacity: disabled || isLoading ? 0.6 : 1,
        transition: 'all 0.2s ease',
        ...variantStyles,
        ...style,
      }}
      {...rest}
    >
      {isLoading ? (
        <span style={{ display: 'inline-block' }}>...</span>
      ) : (
        <>
          {icon && iconPosition === 'left' && <span style={{ display: 'flex', alignItems: 'center' }}>{icon}</span>}
          <span>{children}</span>
          {icon && iconPosition === 'right' && <span style={{ display: 'flex', alignItems: 'center' }}>{icon}</span>}
        </>
      )}
    </button>
  );
};
