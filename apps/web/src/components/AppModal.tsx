import React, { useEffect, useRef } from 'react';
import closeSvg from '../assets/figma/close.svg';
import './AppModal.css';

export interface AppModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  variant?: 'center' | 'drawer';
  state?: 'open' | 'closed';
  size?: 'sm' | 'md' | 'lg' | 'xl';
  showCloseButton?: boolean;
  backdropStyle?: React.CSSProperties;
  backdropClassName?: string;
  dialogStyle?: React.CSSProperties;
}

export const AppModal: React.FC<AppModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  size = 'md',
  showCloseButton = true,
  backdropStyle,
  backdropClassName = '',
  dialogStyle
}) => {
  const modalRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!isOpen) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    const focusable = () => Array.from(modalRef.current?.querySelectorAll<HTMLElement>(
      'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]'
    ) || []);
    (focusable()[0] || modalRef.current)?.focus();
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        closeRef.current();
      }
      if (e.key === 'Tab') {
        const items = focusable(), first = items[0], last = items[items.length - 1];
        if (!first) { e.preventDefault(); modalRef.current?.focus(); }
        else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const maxWidths = {
    sm: '440px',
    md: '600px',
    lg: '795px',
    xl: '960px'
  };

  return (
    <div
      className={`modal-backdrop ${backdropClassName}`}
      style={backdropStyle}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? 'app-modal-title' : undefined}
    >
      <div
        ref={modalRef}
        tabIndex={-1}
        className="modal-dialog"
        style={{ maxWidth: maxWidths[size], ...dialogStyle }}
      >
        {(title || showCloseButton) && (
          <div className="modal-header">
            {title && (
              <h2 id="app-modal-title" className="modal-title">
                {title}
              </h2>
            )}
            {showCloseButton && (
              <button
                type="button"
                onClick={onClose}
                className="modal-close-btn"
                aria-label="Close modal"
              >
                <img src={closeSvg} alt="" style={{ width: '20px', height: '20px' }} />
              </button>
            )}
          </div>
        )}
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
};
