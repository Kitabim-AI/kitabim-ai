import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { Pagination } from '@/src/components/common/Pagination';
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

  expect(screen.getByText('pagination.showingLabel')).toBeInTheDocument();
  expect(screen.getByText('admin.users.pagination')).toBeInTheDocument();
  expect(screen.getByDisplayValue('10')).toBeInTheDocument();
});

test('Pagination handles page change', () => {
  const onPageChange = vi.fn();
  const { container } = render(
    <Pagination
      page={1}
      pageSize={10}
      totalItems={25}
      onPageChange={onPageChange}
      onPageSizeChange={vi.fn()}
    />
  );

  const buttons = container.querySelectorAll('button');
  fireEvent.click(buttons[buttons.length - 1]);
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
  const { container, rerender } = render(
    <Pagination
      page={1}
      pageSize={10}
      totalItems={10}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
    />
  );

  let buttons = container.querySelectorAll('button');
  expect(buttons[0]).toBeDisabled();
  expect(buttons[buttons.length - 1]).toBeDisabled();

  rerender(
    <Pagination
      page={2}
      pageSize={10}
      totalItems={25}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
    />
  );

  buttons = container.querySelectorAll('button');
  expect(buttons[0]).not.toBeDisabled();
  expect(buttons[buttons.length - 1]).not.toBeDisabled();
});
