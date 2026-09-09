import React from 'react';

export interface TabItem {
  id: string;
  label: string;
  count?: number;
  icon?: React.ReactNode | string;
}

export interface AppLineTabProps {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
}

export const AppLineTab: React.FC<AppLineTabProps> = ({ items, activeId, onChange }) => {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      borderBottom: '1px solid #EEEEEE',
      width: '100%',
      overflowX: 'auto',
      scrollbarWidth: 'none',
      background: '#FFFFFF',
    }}>
      {items.map((tab) => {
        const isActive = tab.id === activeId;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              padding: '14px 20px',
              background: 'transparent',
              border: 'none',
              borderBottom: isActive ? '2px solid #4C22F4' : '2px solid transparent',
              color: isActive ? '#2D2D34' : '#AFAFB8',
              fontWeight: isActive ? 700 : 500,
              fontSize: '16px',
              fontFamily: 'inherit',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              transition: 'all 0.2s ease',
              marginBottom: '-1px'
            }}
            onMouseEnter={(e) => {
              if (!isActive) e.currentTarget.style.color = '#2D2D34';
            }}
            onMouseLeave={(e) => {
              if (!isActive) e.currentTarget.style.color = '#AFAFB8';
            }}
          >
            <span>{tab.label}</span>
            {tab.count !== undefined && (
              <span style={{
                fontSize: '12px',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '9999px',
                background: isActive ? '#F0EDFF' : '#F5F5F5',
                color: isActive ? '#4C22F4' : '#888888'
              }}>
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
};
