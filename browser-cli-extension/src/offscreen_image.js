/** DOM image decoding preserves screenshot ICC profiles before sRGB encoding. */
export async function cropImage(dataBase64, {rectangle, enclosing, zoom, density, format}) {
  const image = new Image();
  await new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = () => reject(new Error('Could not decode the screenshot for cropping.'));
    image.src = `data:image/png;base64,${dataBase64}`;
  });
  const width = Math.max(1, Math.round(rectangle.width * density));
  const height = Math.max(1, Math.round(rectangle.height * density));
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const pixelsPerDip = density / zoom;
  canvas.getContext('2d', {colorSpace:'srgb'}).drawImage(image,
    (rectangle.x * zoom - enclosing.x) * pixelsPerDip,
    (rectangle.y * zoom - enclosing.y) * pixelsPerDip,
    rectangle.width * density, rectangle.height * density,
    0, 0, width, height);
  const result = canvas.toDataURL(`image/${format}`);
  if (!result.startsWith(`data:image/${format};base64,`)) throw new Error('Could not encode the cropped screenshot.');
  return {data_base64:result.split(',')[1]};
}
