import multer from "multer";
// Browsers send unlabelled multipart filenames as UTF-8. Multer defaults to
// Latin-1; decoding at this boundary also preserves names forwarded to Python.
const uploadOptions: multer.Options & { defParamCharset: string } = {
  storage: multer.memoryStorage(),
  defParamCharset: "utf8",
  limits: { fileSize: 50 * 1024 * 1024, files: 8 },
};
export const upload = multer(uploadOptions);
