import {describe, expect, it} from 'vitest';
import {envelopeLevelAtFrame, envelopeVolumeAtFrame, staticTrackVolume} from './envelope';

const FPS = 24;

describe('envelopeLevelAtFrame', () => {
	it('без точек держит единицу', () => {
		expect(envelopeLevelAtFrame(10, [], FPS)).toBe(1);
	});

	it('до первой точки держит её уровень', () => {
		// огибающая описывает изменения, а не границы звучания
		expect(envelopeLevelAtFrame(0, [[1, 0.2], [2, 1]], FPS)).toBe(0.2);
	});

	it('после последней точки держит её уровень', () => {
		expect(envelopeLevelAtFrame(FPS * 10, [[0, 1], [2, 0.3]], FPS)).toBe(0.3);
	});

	it('между точками интерполирует линейно', () => {
		// 1 секунда из двух между [0,0] и [2,1] -> ровно середина
		expect(envelopeLevelAtFrame(FPS, [[0, 0], [2, 1]], FPS)).toBeCloseTo(0.5);
	});

	it('две точки в одной секунде дают скачок, а не деление на ноль', () => {
		// В момент скачка новый уровень уже действует, старый остаётся строго до
		// него. Главное здесь — конечное число: нулевой интервал между точками не
		// должен превращаться в деление на ноль.
		const envelope: [number, number][] = [[0, 0.1], [1, 0.1], [1, 1]];
		expect(envelopeLevelAtFrame(FPS - 1, envelope, FPS)).toBeCloseTo(0.1);
		const atJump = envelopeLevelAtFrame(FPS, envelope, FPS);
		expect(Number.isFinite(atJump)).toBe(true);
		expect(atJump).toBe(1);
	});

	it('приближение и отдаление читаются как рост и спад', () => {
		const approach: [number, number][] = [[0, 0.1], [4, 1]];
		expect(envelopeLevelAtFrame(0, approach, FPS)).toBeLessThan(
			envelopeLevelAtFrame(FPS * 3, approach, FPS),
		);
		const recede: [number, number][] = [[0, 1], [4, 0.1]];
		expect(envelopeLevelAtFrame(0, recede, FPS)).toBeGreaterThan(
			envelopeLevelAtFrame(FPS * 3, recede, FPS),
		);
	});
});

describe('envelopeVolumeAtFrame', () => {
	it('умножает базовую громкость, а не заменяет её', () => {
		// иначе огибающая на одной реплике сломала бы баланс слоёв всего эпизода
		expect(envelopeVolumeAtFrame(0, [[0, 0.5]], 0.7, FPS)).toBeCloseTo(0.35);
	});

	it('пустая огибающая оставляет базовую громкость как есть', () => {
		expect(envelopeVolumeAtFrame(5, [], 0.35, FPS)).toBe(0.35);
	});
});

describe('staticTrackVolume', () => {
	it('без огибающей возвращает число, а не функцию', () => {
		// функция вызывалась бы на каждом кадре рендера — платить за это там,
		// где уровень постоянный, незачем
		expect(staticTrackVolume(0.7, undefined, FPS)).toBe(0.7);
		expect(staticTrackVolume(0.7, [], FPS)).toBe(0.7);
	});

	it('с огибающей возвращает функцию, умножающую базовую громкость', () => {
		const v = staticTrackVolume(0.7, [[0, 0], [2, 1]], FPS);
		expect(typeof v).toBe('function');
		expect((v as (f: number) => number)(0)).toBeCloseTo(0);
		expect((v as (f: number) => number)(FPS * 2)).toBeCloseTo(0.7);
	});
});
