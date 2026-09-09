import React from 'react';

export const LoadingState: React.FC<{ message?: string }> = ({ message = 'Investigating narrative memory...' }) => (
  <div style={{
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '60px 20px',
    color: '#8b949e',
    textAlign: 'center'
  }}>
    <div style={{
      width: '40px',
      height: '40px',
      border: '3px solid #D2992233',
      borderTopColor: '#d29922',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite',
      marginBottom: '16px'
    }} />
    <p style={{ margin: 0, fontSize: '15px', letterSpacing: '0.5px' }}>{message}</p>
    <style>{`
      @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
      }
    `}</style>
  </div>
);

export const ErrorState: React.FC<{
  title?: string;
  message?: string;
  statusCode?: number;
  onRetry?: () => void;
}> = ({
  title = 'Forensic Inspection Failed',
  message = 'An unexpected error occurred while retrieving narrative records.',
  statusCode,
  onRetry
}) => (
  <div role="alert" className="feedback-error" style={{
    background: '#F8514914',
    border: '1px solid #F851494C',
    borderRadius: '8px',
    padding: '32px 24px',
    margin: '24px 0',
    textAlign: 'center',
    color: '#f0f6fc'
  }}>
    <div style={{ fontSize: '28px', marginBottom: '8px' }}>⚠️</div>
    {statusCode && (
      <div style={{
        display: 'inline-block',
        background: '#f85149',
        color: '#0d1117',
        fontSize: '12px',
        fontWeight: 'bold',
        padding: '2px 8px',
        borderRadius: '4px',
        marginBottom: '12px'
      }}>
        HTTP {statusCode}
      </div>
    )}
    <h3 style={{ margin: '0 0 8px 0', color: '#ff7b72', fontSize: '18px' }}>{title}</h3>
    <p style={{ margin: '0 0 20px 0', color: '#8b949e', fontSize: '14px', maxWidth: '500px', marginLeft: 'auto', marginRight: 'auto' }}>
      {message}
    </p>
    {onRetry && (
      <button
        onClick={onRetry}
        style={{
          background: '#238636',
          border: '1px solid #F0F6FC1A',
          color: '#ffffff',
          padding: '8px 20px',
          borderRadius: '6px',
          cursor: 'pointer',
          fontWeight: 600,
          fontSize: '14px'
        }}
      >
        Retry Inspection
      </button>
    )}
  </div>
);

export const EmptyState: React.FC<{
  title?: string;
  message?: string;
  actionText?: string;
  onAction?: () => void;
}> = ({
  title = 'No Narrative Records Found',
  message = 'No evidence or proofs match the current forensic criteria or reveal cutoff.',
  actionText,
  onAction
}) => (
  <div className="feedback-empty" style={{
    background: '#161B2299',
    border: '1px dashed #30363d',
    borderRadius: '8px',
    padding: '48px 24px',
    margin: '24px 0',
    textAlign: 'center',
    color: '#8b949e'
  }}>
    <div style={{ fontSize: '32px', marginBottom: '12px' }}>🔍</div>
    <h3 style={{ margin: '0 0 8px 0', color: '#c9d1d9', fontSize: '16px' }}>{title}</h3>
    <p style={{ margin: '0 0 20px 0', fontSize: '14px', maxWidth: '440px', marginLeft: 'auto', marginRight: 'auto' }}>
      {message}
    </p>
    {actionText && onAction && (
      <button
        onClick={onAction}
        style={{
          background: '#21262d',
          border: '1px solid #30363d',
          color: '#58a6ff',
          padding: '8px 16px',
          borderRadius: '6px',
          cursor: 'pointer',
          fontSize: '13px',
          fontWeight: 500
        }}
      >
        {actionText}
      </button>
    )}
  </div>
);
