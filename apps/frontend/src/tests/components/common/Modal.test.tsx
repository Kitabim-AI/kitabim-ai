import { Modal } from '@/src/components/common/Modal';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { fireEvent, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

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

test('Modal calls confirm and close correctly', () => {
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

  fireEvent.click(screen.getByText('modal.confirm'));
  expect(onConfirm).toHaveBeenCalled();

  fireEvent.click(screen.getByText('common.cancel'));
  expect(onClose).toHaveBeenCalled();
});

test('Modal alert type behavior', () => {
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

  fireEvent.click(screen.getByText('modal.ok'));
  expect(onClose).toHaveBeenCalled();
});
