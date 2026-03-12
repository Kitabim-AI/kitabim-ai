import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { Modal } from '@/src/components/common/Modal';
import { expect, test, vi } from 'vitest';
import React from 'react';

test('Modal does not render when isOpen is false', () => {
  const { container } = render(
    <Modal
      isOpen={false}
      title="Test Title"
      message="Test Message"
      type="alert"
      onClose={vi.fn()}
    />
  );
  expect(container.firstChild).toBeNull();
});

test('Modal renders title and message', () => {
  render(
    <Modal
      isOpen={true}
      title="Delete Book"
      message="Are you sure you want to delete this book?"
      type="confirm"
      onClose={vi.fn()}
    />
  );

  expect(screen.getByText('Delete Book')).toBeInTheDocument();
  expect(screen.getByText(/Are you sure/i)).toBeInTheDocument();
});

test.skip('Modal calls confirm and close correctly', () => {
  const onConfirm = vi.fn();
  const onClose = vi.fn();

  render(
    <Modal
      isOpen={true}
      title="Confirm Title"
      message="Message"
      type="confirm"
      onConfirm={onConfirm}
      onClose={onClose}
    />
  );

  const confirmBtn = screen.getByText('Confirm');
  const cancelBtn = screen.getByText('Cancel');

  fireEvent.click(confirmBtn);
  expect(onConfirm).toHaveBeenCalled();

  fireEvent.click(cancelBtn);
  expect(onClose).toHaveBeenCalled();
});

test.skip('Modal alert type behavior', () => {
  const onClose = vi.fn();
  render(
    <Modal
      isOpen={true}
      title="Alert"
      message="Alert Message"
      type="alert"
      onClose={onClose}
    />
  );

  const understoodBtn = screen.getByText('Understood');
  fireEvent.click(understoodBtn);
  expect(onClose).toHaveBeenCalled();
});
