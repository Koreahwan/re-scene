import React from 'react';

export interface CategoryChipProps {
  label: string;
  count?: number;
  isSelected?: boolean;
  onClick?: () => void;
  size?: 'sm' | 'md' | 'lg';
}

export const CategoryChip: React.FC<CategoryChipProps> = ({
  label,
  count,
  isSelected = false,
  onClick,
  size = 'md'
}) => {
  const sizeStyles = {
    sm: { padding: '4px 12px', fontSize: '13px', height: '28px' },
    md: { padding: '6px 16px', fontSize: '14px', height: '34px' },
    lg: { padding: '8px 20px', fontSize: '15px', height: '40px' },
  }[size];

  return (
    <button
      onClick={onClick}
      style={{
        ...sizeStyles,
        borderRadius: '9999px',
        fontWeight: isSelected ? 600 : 500,
        color: isSelected ? '#FFFFFF' : '#555555',
        background: isSelected ? '#4C22F4' : '#F5F5F5',
        border: isSelected ? '1px solid #4C22F4' : '1px solid #EEEEEE',
        cursor: 'pointer',
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        fontFamily: 'inherit',
        transition: 'all 0.2s ease',
      }}
      onMouseEnter={(e) => {
        if (!isSelected) {
          e.currentTarget.style.background = '#EEEEEE';
          e.currentTarget.style.color = '#2D2D34';
        }
      }}
      onMouseLeave={(e) => {
        if (!isSelected) {
          e.currentTarget.style.background = '#F5F5F5';
          e.currentTarget.style.color = '#555555';
        }
      }}
    >
      <span>{label}</span>
      {count !== undefined && (
        <span style={{
          fontSize: '11px',
          fontWeight: 700,
          padding: '1px 6px',
          borderRadius: '9999px',
          background: isSelected ? '#FFFFFF30' : '#E5E5E5',
          color: isSelected ? '#FFFFFF' : '#888888'
        }}>
          {count}
        </span>
      )}
    </button>
  );
};
