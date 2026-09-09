import type { HTMLAttributes } from 'react';

// Text inputs match the plain Figma field on click; Tab navigation stays visible.
export const authInputModality: HTMLAttributes<HTMLElement> = {
  onPointerDownCapture: event => {
    event.currentTarget.dataset.inputModality = 'pointer';
  },
  onKeyDownCapture: event => {
    if (event.key === 'Tab') event.currentTarget.dataset.inputModality = 'keyboard';
  },
  onBlurCapture: event => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      delete event.currentTarget.dataset.inputModality;
    }
  },
};
