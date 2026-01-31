import { render, screen, fireEvent } from '@testing-library/react';
import { Pagination } from '../components/common/Pagination';
import { expect, test, vi } from 'vitest';
import React from 'react';

test('Pagination renders statistics correctly', () => {
  render(
    <Pagination
      page={1}
      pageSize={10}
      totalItems={25}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
    />
  );

  expect(screen.getByText(/Showing/i)).toBeInTheDocument();
  // Using getAllByText because '1' appears in statistics and in page button
  expect(screen.getAllByText('1').length).toBeGreaterThan(0);
  expect(screen.getAllByText('10').length).toBeGreaterThan(0);
  expect(screen.getByText('25')).toBeInTheDocument();
});

test('Pagination handles page change', () => {
  const onPageChange = vi.fn();
  render(
    <Pagination
      page={1}
      pageSize={10}
      totalItems={25}
      onPageChange={onPageChange}
      onPageSizeChange={vi.fn()}
    />
  );

  const nextBtn = screen.getByTitle('Next Page');
  fireEvent.click(nextBtn);
  expect(onPageChange).toHaveBeenCalledWith(2);
});

test('Pagination handles page size change', () => {
  const onPageSizeChange = vi.fn();
  render(
    <Pagination
      page={1}
      pageSize={10}
      totalItems={25}
      onPageChange={vi.fn()}
      onPageSizeChange={onPageSizeChange}
    />
  );

  const select = screen.getByRole('combobox');
  fireEvent.change(select, { target: { value: '20' } });
  expect(onPageSizeChange).toHaveBeenCalledWith(20);
});

test('Pagination disables buttons correctly', () => {
  const { rerender } = render(
    <Pagination
      page={1}
      pageSize={10}
      totalItems={10}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
    />
  );

  expect(screen.getByTitle('Previous Page')).toBeDisabled();
  expect(screen.getByTitle('Next Page')).toBeDisabled();

  rerender(
    <Pagination
      page={2}
      pageSize={10}
      totalItems={25}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
    />
  );

  expect(screen.getByTitle('Previous Page')).not.toBeDisabled();
  expect(screen.getByTitle('Next Page')).not.toBeDisabled();
});
