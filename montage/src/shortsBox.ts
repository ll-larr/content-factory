/**
 * Геометрия шортса: куда лечь видео, баннеру и субтитрам.
 *
 * Исходник бывает разной формы. Отрезок 16:9 вписывается по ширине, и сверху со
 * снизу остаются равные полосы — в них и живёт текст. Но модель может отдать и
 * вертикальный кадр: тогда полос не остаётся вовсе, и текст обязан лечь ПОВЕРХ
 * картинки, иначе баннер с субтитрами просто исчезнут (замечено пользователем
 * 2026-09-02 на первом же просмотре).
 *
 * Граница между режимами проходит не по «9:16 или нет», а по тому, помещается ли
 * в полосу строка текста: полоса в полсотни пикселей бесполезна.
 */

export const CANVAS_WIDTH = 1080;
export const CANVAS_HEIGHT = 1920;

/** Полоса тоньше этого текст не удержит — уходим в наложение. */
export const MIN_BAND = 200;

/** Низ экрана занят панелью площадки (TikTok, Shorts, Reels). */
export const PLATFORM_UI_BOTTOM = 200;

export type Band = {top: number; height: number};

/** Холст горизонтального эпизода. */
export const WIDE_WIDTH = 1920;
export const WIDE_HEIGHT = 1080;

/**
 * Полоса субтитров горизонтального эпизода: нижняя часть кадра с отступом от
 * края. Не вынесена за пределы картинки, как у шортса в letterbox: полей у
 * 16:9 нет, текст всегда лежит поверх — отсюда `overlay` у плашки.
 */
export const WIDE_CAPTION_BAND: Band = {top: WIDE_HEIGHT - 260, height: 180};

export type ShortsBox = {
	mode: 'letterbox' | 'fullscreen';
	videoTop: number;
	videoHeight: number;
	bannerBand: Band;
	captionBand: Band;
};

export const shortsBox = (
	sourceWidth: number,
	sourceHeight: number,
): ShortsBox => {
	const fullscreen = (): ShortsBox => ({
		mode: 'fullscreen',
		videoTop: 0,
		videoHeight: CANVAS_HEIGHT,
		// Наложение: баннер под верхней кромкой, субтитры над панелью площадки.
		bannerBand: {top: 120, height: 260},
		captionBand: {top: 1360, height: 320},
	});

	if (sourceWidth <= 0 || sourceHeight <= 0) return fullscreen();

	const videoHeight = (sourceHeight * CANVAS_WIDTH) / sourceWidth;
	const band = (CANVAS_HEIGHT - videoHeight) / 2;
	if (band < MIN_BAND) return fullscreen();

	return {
		mode: 'letterbox',
		videoTop: band,
		videoHeight,
		bannerBand: {top: 0, height: band},
		captionBand: {top: band + videoHeight, height: band},
	};
};
