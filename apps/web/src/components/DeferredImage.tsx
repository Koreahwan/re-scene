import React, { useState, useEffect, useRef, useCallback } from 'react';

export interface DeferredImageProps extends React.ImgHTMLAttributes<HTMLImageElement> {
  rootMargin?: string;
  fallbackSrc?: string;
  maxRetries?: number;
}

/**
 * DeferredImage:
 * Defers attaching image src until near the viewport using IntersectionObserver.
 * Implements bounded backoff retry (up to maxRetries, default 2) on transient loading failures.
 *
 * NOTE: To force the browser to genuinely perform a network re-fetch, the DOM src
 * must be cleared while waiting for the backoff timer, and re-attached when the timer fires.
 *
 * Enforces:
 * - Upper bound on retries (maxRetries = 2, total attempts <= 3).
 * - Immediate timer cleanup on unmount and when src prop changes.
 * - Loop prevention on fallbackSrc failure.
 * - Lowercase fetchpriority DOM prop to prevent React 18 warnings.
 */
export const DeferredImage: React.FC<DeferredImageProps> = (props) => {
  const {
    src,
    alt = '',
    fallbackSrc,
    rootMargin = '150px',
    maxRetries = 2,
    onError,
    style,
    fetchPriority,
    ...rest
  } = props;

  const [isNearViewport, setIsNearViewport] = useState<boolean>(false);
  const [retryAttempt, setRetryAttempt] = useState<number>(0);
  const [isRetrying, setIsRetrying] = useState<boolean>(false);
  const [isFallbackActive, setIsFallbackActive] = useState<boolean>(false);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset retry state and clear pending timers whenever target src changes
  useEffect(() => {
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    setRetryAttempt(0);
    setIsRetrying(false);
    setIsFallbackActive(false);
  }, [src]);

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
    };
  }, []);

  // IntersectionObserver to detect when near viewport
  useEffect(() => {
    if (isNearViewport) return;

    if (typeof window === 'undefined' || !('IntersectionObserver' in window)) {
      setIsNearViewport(true);
      return;
    }

    const element = imgRef.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setIsNearViewport(true);
            observer.disconnect();
            break;
          }
        }
      },
      { rootMargin }
    );

    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, [rootMargin, isNearViewport]);

  const handleError = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement, Event>) => {
      // If we are already displaying the fallback, do not loop retries on fallback
      if (isFallbackActive) {
        if (onError) onError(e);
        return;
      }

      // If retries remain for original src
      if (retryAttempt < maxRetries && src) {
        const nextAttempt = retryAttempt + 1;
        // Exponential backoff: ~300ms for attempt 1, ~600ms for attempt 2
        const delay = 300 * Math.pow(2, retryAttempt) + Math.floor(Math.random() * 50);

        // Immediately clear DOM src during the backoff delay
        setIsRetrying(true);

        if (retryTimerRef.current) {
          clearTimeout(retryTimerRef.current);
        }

        retryTimerRef.current = setTimeout(() => {
          setRetryAttempt(nextAttempt);
          setIsRetrying(false); // Re-attaches original src, forcing browser to issue fresh network request
        }, delay);
        return;
      }

      // Retries exhausted: switch to fallback if available
      if (fallbackSrc) {
        setIsFallbackActive(true);
        setIsRetrying(false);
      }

      if (onError) {
        onError(e);
      }
    },
    [retryAttempt, maxRetries, src, fallbackSrc, isFallbackActive, onError]
  );

  let effectiveSrc: string | undefined = undefined;
  if (isNearViewport) {
    if (isFallbackActive) {
      effectiveSrc = fallbackSrc;
    } else if (!isRetrying) {
      effectiveSrc = src;
    }
  }

  return (
    <img
      ref={imgRef}
      src={effectiveSrc}
      alt={alt}
      loading={isNearViewport ? 'eager' : 'lazy'}
      decoding="async"
      data-deferred={!isNearViewport ? 'true' : 'false'}
      data-retried={retryAttempt > 0 ? String(retryAttempt) : undefined}
      data-retrying={isRetrying ? 'true' : undefined}
      onError={handleError}
      style={style}
      {...(fetchPriority ? { fetchpriority: fetchPriority as any } : {})}
      {...rest}
    />
  );
};

export default DeferredImage;

