# Downloads and exports

Read the live command help first. Download/export commands often have remote
`access=read` but still create local files. Choose an output path under the
current session directory, prefer a relative path, and report the resulting file
to the main Agent so the chat attachment list can expose it.

Do not infer download parameters from command names. Some adapters require
`yt-dlp`, local credentials, or a Browser Bridge downloads API. Verify the file
exists, size/type, and that it is not an HTML login/error page before reporting
success. Treat subtitles, transcript, article, media, conversation, and export
commands as separate help lookups.

Never return cookies, signed URLs, authorization headers, or private response
bodies as part of a download report.
