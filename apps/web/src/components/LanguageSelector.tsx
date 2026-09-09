import React, { useState, useRef, useEffect } from 'react';
import { useLocale } from '../i18n/LocaleProvider';
import { SupportedLocale } from '../i18n/localeTypes';

interface LanguageSelectorProps {
  variant?: 'navbar' | 'auth' | 'mobile';
  className?: string;
}

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({ variant = 'navbar', className = '' }) => {
  const { locale, setLocale, t } = useLocale();
  const [isOpen, setIsOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(0);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listboxRef = useRef<HTMLUListElement>(null);
  const optionRefs = useRef<(HTMLLIElement | null)[]>([]);

  const options: Array<{ code: SupportedLocale; label: string; shortLabel: string }> = [
    { code: 'en-US', label: 'English', shortLabel: 'EN' }
  ];

  // Sync focused index with active locale
  useEffect(() => {
    const idx = options.findIndex(o => o.code === locale);
    if (idx !== -1) {
      setFocusedIndex(idx);
    }
  }, [locale]);

  // Focus the option when dropdown opens
  useEffect(() => {
    if (isOpen) {
      const idx = options.findIndex(o => o.code === locale);
      const targetIdx = idx !== -1 ? idx : 0;
      setFocusedIndex(targetIdx);
      setTimeout(() => {
        optionRefs.current[targetIdx]?.focus();
      }, 50);
    }
  }, [isOpen, locale]);

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const handleSelect = (code: SupportedLocale) => {
    setLocale(code);
    setIsOpen(false);
    triggerRef.current?.focus();
  };

  // Full WAI-ARIA Keyboard Navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      setIsOpen(false);
      triggerRef.current?.focus();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
      } else {
        const nextIdx = (focusedIndex + 1) % options.length;
        setFocusedIndex(nextIdx);
        optionRefs.current[nextIdx]?.focus();
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
      } else {
        const prevIdx = (focusedIndex - 1 + options.length) % options.length;
        setFocusedIndex(prevIdx);
        optionRefs.current[prevIdx]?.focus();
      }
    } else if (e.key === 'Home') {
      e.preventDefault();
      if (isOpen) {
        setFocusedIndex(0);
        optionRefs.current[0]?.focus();
      }
    } else if (e.key === 'End') {
      e.preventDefault();
      if (isOpen) {
        const lastIdx = options.length - 1;
        setFocusedIndex(lastIdx);
        optionRefs.current[lastIdx]?.focus();
      }
    } else if (e.key === 'Enter' || e.key === ' ') {
      if (isOpen) {
        e.preventDefault();
        handleSelect(options[focusedIndex].code);
      }
    }
  };

  const currentOption = options.find(o => o.code === locale) || options[0];

  return (
    <div
      ref={dropdownRef}
      className={`language-selector-wrapper ${className}`}
      style={{ position: 'relative', display: 'inline-block' }}
      onKeyDown={handleKeyDown}
    >
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={t('nav.language')}
        title={t('nav.language')}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: variant === 'mobile' ? '8px 12px' : '6px 10px',
          background: isOpen ? 'var(--bg-surface-raised, #1C2233)' : '#FFFFFF0D',
          border: '1px solid var(--border-default, #FFFFFF24)',
          borderRadius: 'var(--radius-md, 8px)',
          color: 'var(--text-primary, #FFFFFF)',
          fontSize: '13px',
          fontWeight: 600,
          cursor: 'pointer',
          transition: 'all var(--transition-fast, 150ms ease)'
        }}
      >
        {/* Exact Globe Icon SVG (Neutral, no country flags) */}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="2" y1="12" x2="22" y2="12" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
        <span>{currentOption.shortLabel}</span>
        {/* Exact Chevron Icon SVG */}
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform var(--transition-fast, 150ms ease)'
          }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {isOpen && (
        <ul
          ref={listboxRef}
          role="listbox"
          aria-label={t('nav.language')}
          tabIndex={-1}
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            right: 0,
            zIndex: 1000,
            minWidth: '130px',
            background: 'var(--bg-modal, #161C2B)',
            border: '1px solid var(--border-strong, #FFFFFF40)',
            borderRadius: 'var(--radius-md, 8px)',
            boxShadow: 'var(--shadow-lg, 0 10px 15px -3px #000000B2)',
            padding: '4px',
            margin: 0,
            listStyle: 'none'
          }}
        >
          {options.map((opt, index) => {
            const isSelected = opt.code === locale;
            const isFocused = index === focusedIndex;
            return (
              <li
                key={opt.code}
                ref={(el) => (optionRefs.current[index] = el)}
                role="option"
                aria-selected={isSelected}
                tabIndex={isFocused ? 0 : -1}
                onClick={() => handleSelect(opt.code)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 12px',
                  borderRadius: 'var(--radius-sm, 4px)',
                  fontSize: '13px',
                  fontWeight: isSelected ? 700 : 500,
                  color: isSelected ? 'var(--primary-400, #C084FC)' : 'var(--text-primary, #FFFFFF)',
                  background: isSelected ? '#A855F71F' : isFocused ? '#FFFFFF14' : 'transparent',
                  cursor: 'pointer',
                  outline: 'none',
                  transition: 'background var(--transition-fast, 150ms ease)'
                }}
                onMouseEnter={() => setFocusedIndex(index)}
              >
                <span>{opt.label}</span>
                {isSelected && (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
