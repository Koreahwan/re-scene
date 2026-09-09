import React from 'react';

interface SortOptionsProps {
  label: string;
  value: string;
  options: readonly { value: string; label: string; description?: string }[];
  onChange: (value: string) => void;
}

// Figma 553:6852: compact text buttons, with the selected option emphasized.
export function SortOptions({ label, value, options, onChange }: SortOptionsProps) {
  return <div className="catalog-sort-options" role="group" aria-label={label}>
    {options.map(option => <button
      type="button" key={option.value} aria-pressed={value === option.value} title={option.description}
      onClick={() => onChange(option.value)}
    >{option.label}</button>)}
  </div>;
}

export const movieSortOptions = [
  { value: 'newest', label: 'Latest', description: 'Recently added' },
  { value: 'popular', label: 'Popular', description: 'Views in the last 7 days' },
  { value: 'views', label: 'Most Viewed', description: 'All-time views' },
] as const;

export const articleSortOptions = [
  { value: 'latest', label: 'Latest', description: 'Recently published' },
  { value: 'popular', label: 'Popular', description: 'Views in the last 7 days' },
  { value: 'views', label: 'Most Viewed', description: 'All-time views' },
] as const;
