import { useState } from 'react';

interface UserAvatarProps {
  url?: string | null;
  name: string;
  className: string;
}

/**
 * Robust User Avatar component that handles image loading failures.
 * Falls back to name initials with a gradient background if the image fails to load.
 */
export function UserAvatar({ url, name, className }: UserAvatarProps) {
  const [hasError, setHasError] = useState(false);

  if (url && url.trim().length > 0 && !hasError) {
    return (
      <img
        src={url}
        alt={name}
        className={className}
        onError={() => setHasError(true)}
        referrerPolicy="no-referrer"
      />
    );
  }

  // Fallback to initial
  return (
    <div
      className={`${className} bg-gradient-to-br from-[#0369a1] to-[#0284c7] flex items-center justify-center font-normal text-white shadow-lg`}
    >
      {name ? name.charAt(0).toUpperCase() : '?'}
    </div>
  );
}

export default UserAvatar;
