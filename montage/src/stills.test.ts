import {describe, expect, it} from 'vitest';
import {
	placeStills,
	stillOpacity,
	stillSeconds,
	stillZoom,
	stillsDuration,
} from './stills';
import type {MediaFacts} from './metadata';
import type {StillsSettings} from './stills';

const SETTINGS: StillsSettings = {
	minSeconds: 3,
	tailSeconds: 0.6,
	crossfadeSeconds: 0.4,
	zoom: 1.08,
};

const facts = (seconds: number): MediaFacts => ({
	durationInSeconds: seconds,
	fps: 24,
	width: 1280,
	height: 720,
});

describe('длительность кадра', () => {
	it('кадр без реплик висит минимум — молчаливую картинку тоже надо прочитать', () => {
		expect(stillSeconds(1, [], {}, SETTINGS)).toBe(3);
	});

	it('кадр живёт до конца своей реплики плюс хвост', () => {
		const voice = [{segment: 1, offset: 1, file: 'a.mp3'}];
		expect(stillSeconds(1, voice, {'a.mp3': facts(4)}, SETTINGS)).toBeCloseTo(5.6);
	});

	it('считает по последней реплике, а не по первой', () => {
		const voice = [
			{segment: 1, offset: 0, file: 'a.mp3'},
			{segment: 1, offset: 6, file: 'b.mp3'},
		];
		const media = {'a.mp3': facts(2), 'b.mp3': facts(1)};
		expect(stillSeconds(1, voice, media, SETTINGS)).toBeCloseTo(7.6);
	});

	it('чужие реплики не удлиняют кадр', () => {
		const voice = [{segment: 2, offset: 0, file: 'a.mp3'}];
		expect(stillSeconds(1, voice, {'a.mp3': facts(30)}, SETTINGS)).toBe(3);
	});

	it('неизмеренный файл не роняет сборку', () => {
		const voice = [{segment: 1, offset: 1, file: 'нет.mp3'}];
		expect(stillSeconds(1, voice, {}, SETTINGS)).toBe(3);
	});
});

describe('раскладка кадров', () => {
	const stills = [
		{n: 1, file: '001.png'},
		{n: 2, file: '002.png'},
		{n: 3, file: '003.png'},
	];

	it('кадры идут подряд без зазоров и без наложения', () => {
		const placed = placeStills(stills, [], {}, SETTINGS, 24);
		expect(placed.map((s) => s.from)).toEqual([0, 72, 144]);
		expect(placed.every((s) => s.durationInFrames === 72)).toBe(true);
	});

	it('длительность кадра растёт вслед за его репликой', () => {
		const voice = [{segment: 2, offset: 0, file: 'b.mp3'}];
		const placed = placeStills(stills, voice, {'b.mp3': facts(10)}, SETTINGS, 24);
		expect(placed[1].durationInFrames).toBe(Math.round(10.6 * 24));
		expect(placed[2].from).toBe(placed[1].from + placed[1].durationInFrames);
	});

	it('общая длительность — сумма кадров', () => {
		const placed = placeStills(stills, [], {}, SETTINGS, 24);
		expect(stillsDuration(placed)).toBe(216);
	});

	it('кадр никогда не нулевой длины', () => {
		const placed = placeStills([{n: 1, file: 'a.png'}], [], {},
			{...SETTINGS, minSeconds: 0}, 24);
		expect(placed[0].durationInFrames).toBeGreaterThan(0);
	});
});

describe('движение и переходы', () => {
	it('наезд идёт от единицы до объявленного масштаба', () => {
		expect(stillZoom(0, 72, SETTINGS)).toBe(1);
		expect(stillZoom(71, 72, SETTINGS)).toBeCloseTo(1.08);
	});

	it('наезд не выходит за границы при странных значениях', () => {
		expect(stillZoom(999, 72, SETTINGS)).toBeCloseTo(1.08);
		expect(stillZoom(0, 1, SETTINGS)).toBe(1);
	});

	it('кадр появляется и уходит через затемнение', () => {
		expect(stillOpacity(0, 72, SETTINGS, 24)).toBe(0);
		expect(stillOpacity(36, 72, SETTINGS, 24)).toBe(1);
		expect(stillOpacity(71, 72, SETTINGS, 24)).toBe(0);
	});

	it('короткий кадр не мигает: затемнению не хватило бы места', () => {
		expect(stillOpacity(0, 10, SETTINGS, 24)).toBe(1);
	});
});
