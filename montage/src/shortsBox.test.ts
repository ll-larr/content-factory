import {describe, expect, it} from 'vitest';
import {MIN_BAND, shortsBox, WIDE_CAPTION_BAND, WIDE_HEIGHT} from './shortsBox';

const CANVAS_W = 1080;
const CANVAS_H = 1920;

describe('shortsBox: горизонтальный исходник', () => {
	it('16:9 вписывается по ширине, поля сверху и снизу равны', () => {
		const box = shortsBox(1280, 720);
		expect(box.mode).toBe('letterbox');
		expect(box.videoHeight).toBeCloseTo(607.5, 1);
		expect(box.videoTop).toBeCloseTo((CANVAS_H - 607.5) / 2, 1);
		expect(box.bannerBand.top).toBe(0);
		expect(box.bannerBand.height).toBeCloseTo(box.videoTop, 1);
		expect(box.captionBand.top).toBeCloseTo(box.videoTop + box.videoHeight, 1);
	});

	it('нестандартный размер выдачи Runware тоже вписывается', () => {
		// Vidu на Runware отдаёт 1284x716, а не 1280x720.
		const box = shortsBox(1284, 716);
		expect(box.mode).toBe('letterbox');
		expect(box.videoHeight).toBeCloseTo((716 * CANVAS_W) / 1284, 1);
	});

	it('квадрат остаётся letterbox: полос хватает на текст', () => {
		const box = shortsBox(1080, 1080);
		expect(box.mode).toBe('letterbox');
		expect(box.videoTop).toBeCloseTo(420, 1);
	});
});

describe('shortsBox: вертикальный исходник', () => {
	it('9:16 занимает весь экран, текст ложится поверх', () => {
		const box = shortsBox(1080, 1920);
		expect(box.mode).toBe('fullscreen');
		expect(box.videoTop).toBe(0);
		expect(box.videoHeight).toBe(CANVAS_H);
	});

	it('исходник выше 9:16 тоже на весь экран (обрежется по высоте)', () => {
		const box = shortsBox(1080, 2400);
		expect(box.mode).toBe('fullscreen');
		expect(box.videoHeight).toBe(CANVAS_H);
	});

	it('почти вертикальный уходит в fullscreen: полосы были бы уже текста', () => {
		// 1080x1600 дало бы полосы по 160 px — туда не влезет ни баннер, ни строка.
		const box = shortsBox(1080, 1600);
		expect(box.mode).toBe('fullscreen');
	});

	it('граница режимов проходит ровно по минимальной высоте полосы', () => {
		const heightAtBoundary = CANVAS_H - 2 * MIN_BAND;
		expect(shortsBox(CANVAS_W, heightAtBoundary - 2).mode).toBe('letterbox');
		expect(shortsBox(CANVAS_W, heightAtBoundary + 2).mode).toBe('fullscreen');
	});

	it('в fullscreen баннер и субтитры стоят в безопасных зонах', () => {
		const box = shortsBox(1080, 1920);
		// Сверху не под самой кромкой, снизу выше панели площадки.
		expect(box.bannerBand.top).toBeGreaterThan(0);
		expect(box.captionBand.top + box.captionBand.height).toBeLessThan(
			CANVAS_H - 200,
		);
		expect(box.bannerBand.height).toBeGreaterThanOrEqual(MIN_BAND);
		expect(box.captionBand.height).toBeGreaterThanOrEqual(MIN_BAND);
	});
});

describe('shortsBox: вырожденные данные', () => {
	it('нулевой размер не роняет раскладку', () => {
		const box = shortsBox(0, 0);
		expect(box.mode).toBe('fullscreen');
		expect(Number.isFinite(box.videoHeight)).toBe(true);
	});
});

describe('полоса субтитров горизонтального эпизода', () => {
	it('лежит внутри холста и держит строку', () => {
		expect(WIDE_CAPTION_BAND.top).toBeGreaterThan(0);
		expect(WIDE_CAPTION_BAND.top + WIDE_CAPTION_BAND.height)
			.toBeLessThanOrEqual(WIDE_HEIGHT);
		// Ниже MIN_BAND текст не удержать — та же граница, что у шортса.
		expect(WIDE_CAPTION_BAND.height).toBeLessThan(MIN_BAND);
		expect(WIDE_CAPTION_BAND.height).toBeGreaterThan(100);
	});

	it('не наезжает на нижнюю кромку кадра', () => {
		expect(WIDE_HEIGHT - (WIDE_CAPTION_BAND.top + WIDE_CAPTION_BAND.height))
			.toBeGreaterThan(40);
	});
});
