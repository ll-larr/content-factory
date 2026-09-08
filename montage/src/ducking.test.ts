import {describe, expect, it} from 'vitest';
import {duckingOptions, musicVolumeAtFrame} from './ducking';
import type {Interval} from './ducking';

// Опции как в реальном листе: база 0.35, приглушение до 0.4842 от неё,
// attack 5 мс, release 1050 мс, 24 кадра в секунду.
const opts = duckingOptions(
	{gain: 0.4842, attackMs: 5, releaseMs: 1050},  // значения теста, не продакшн
	0.35,
	24,
);

const DUCKED = 0.35 * 0.4842; // 0.16947

describe('musicVolumeAtFrame', () => {
	it('без речи держит базовую громкость', () => {
		expect(musicVolumeAtFrame(50, [], opts)).toBeCloseTo(0.35, 5);
	});

	it('внутри реплики приглушает до -6.3 dB от базы', () => {
		const intervals: Interval[] = [{from: 24, to: 72}];
		expect(musicVolumeAtFrame(48, intervals, opts)).toBeCloseTo(DUCKED, 5);
	});

	it('до реплики громкость ещё базовая', () => {
		expect(musicVolumeAtFrame(23, [{from: 24, to: 72}], opts)).toBeCloseTo(
			0.35,
			5,
		);
	});

	it('после release возвращается к базе', () => {
		// release 1050 мс при 24 fps = 25.2 кадра.
		expect(musicVolumeAtFrame(98, [{from: 24, to: 72}], opts)).toBeCloseTo(
			0.35,
			5,
		);
	});

	it('на середине release громкость между приглушённой и базовой', () => {
		const v = musicVolumeAtFrame(84, [{from: 24, to: 72}], opts);
		expect(v).toBeGreaterThan(DUCKED);
		expect(v).toBeLessThan(0.35);
	});

	it('между двумя близкими репликами музыка не успевает всплыть', () => {
		// Пауза 6 кадров (0.25 c) при release 25.2 кадра: подложка едва трогается
		// с места и тут же ныряет обратно. Так вёл себя и компрессор в ffmpeg —
		// он интервалы не склеивал, а отпускал по release.
		const intervals: Interval[] = [
			{from: 24, to: 48},
			{from: 54, to: 78},
		];
		const inGap = musicVolumeAtFrame(51, intervals, opts);
		expect(inGap).toBeLessThan(DUCKED * 1.2);
	});

	it('перекрывающиеся речь и SFX не приглушают дважды', () => {
		const intervals: Interval[] = [
			{from: 24, to: 72},
			{from: 30, to: 60},
		];
		expect(musicVolumeAtFrame(45, intervals, opts)).toBeCloseTo(DUCKED, 5);
	});

	it('attack при 24 fps короче кадра, приглушение приходит сразу', () => {
		// 5 мс это 0.12 кадра: рампа существует в математике, но на сетке кадров
		// не видна. Параметр сохранён, потому что fps задаётся выдачей модели.
		expect(musicVolumeAtFrame(24, [{from: 24, to: 72}], opts)).toBeCloseTo(
			DUCKED,
			5,
		);
	});
});

describe('duckingOptions', () => {
	it('переводит миллисекунды в кадры по fps композиции', () => {
		const o = duckingOptions({gain: 0.5, attackMs: 1000, releaseMs: 2000}, 1, 30);
		expect(o.attackFrames).toBe(30);
		expect(o.releaseFrames).toBe(60);
		expect(o.duckedVolume).toBe(0.5);
	});
});
