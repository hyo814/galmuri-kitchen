/**
 * 사진을 긴 변 maxSide px 이하 JPEG로 줄인다(스펙 6절: 업로드·AI 비용 절약).
 * 폰 사진의 회전(EXIF) 정보를 반영하고, 디코딩에 실패하면(예: 브라우저가 못 읽는 형식) 원본 파일을 그대로 쓴다.
 */
export async function resizeImage(file: Blob, maxSide = 1568): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const context = canvas.getContext("2d");
    if (!context) {
      bitmap.close();
      return file;
    }
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
    return blob ?? file;
  } catch {
    return file;
  }
}
