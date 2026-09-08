import {Config} from '@remotion/cli/config';

// Кодек по умолчанию — h264, как у прежней сборки на ffmpeg (assemble.py: libx264
// + yuv420p). Менять только вместе с проверкой, что результат играется там же,
// где игрался прежний.
Config.setVideoImageFormat('jpeg');
Config.setCodec('h264');
Config.setPixelFormat('yuv420p');
