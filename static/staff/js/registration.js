// Match the existing server upload limit; server validation remains authoritative.
document.addEventListener('DOMContentLoaded', () => {
  const photo = document.getElementById('photo');
  const error = document.getElementById('photo-error');
  if (!photo || !error) return;
  photo.addEventListener('change', () => {
    const oversized = photo.files.length && photo.files[0].size > 400 * 1024;
    const message = oversized ? 'Choose a photo no larger than 400 KiB.' : '';
    photo.setCustomValidity(message);
    error.textContent = message;
    error.hidden = !oversized;
  });
});
