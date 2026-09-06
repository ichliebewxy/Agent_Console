/** Transport-independent upload data; Multer files satisfy these contracts. */
export type UploadedFile = { originalname: string; buffer: Buffer };
export type UploadedImage = UploadedFile & { mimetype: string };
