/**
 * Приглушение музыки под речью и SFX — огибающая громкости.
 *
 * Прежде это делал фильтр ffmpeg
 * `sidechaincompress=threshold=0.01:ratio=20:attack=5:release=1050`, выбранный
 * пользователем на слух из семи вариантов (живая калибровка 2026-09-02); суммарное
 * приглушение относительно недакнутой подложки — −6.3 dB.
 *
 * Компрессор угадывает по амплитуде, где речь. Нам гадать не нужно: интервалы
 * речи известны точно из монтажного листа. Поэтому здесь прямая огибающая с теми
 * же attack и release.
 *
 * Интервалы СОЗНАТЕЛЬНО не склеиваются. Компрессор их тоже не склеивал: между
 * двумя близкими репликами он начинал отпускать и не успевал вернуть громкость.
 * Слияние дало бы ровное плато вместо этого движения — звук, которого пользователь
 * не выбирал. Поэтому берётся минимум по огибающим отдельных интервалов: самое
 * глубокое приглушение в этом кадре и выигрывает.
 */

export type Interval = {from: number; to: number};

export type DuckingOptions = {
	baseVolume: number;
	duckedVolume: number;
	attackFrames: number;
	releaseFrames: number;
};

export const duckingOptions = (
	duck: {gain: number; attackMs: number; releaseMs: number},
	baseVolume: number,
	fps: number,
): DuckingOptions => ({
	baseVolume,
	duckedVolume: baseVolume * duck.gain,
	attackFrames: (duck.attackMs * fps) / 1000,
	releaseFrames: (duck.releaseMs * fps) / 1000,
});

/**
 * Доля приглушения одного интервала на кадре: 1 — не тронуто, 0 — полностью
 * приглушено. Рампы линейные, как у компрессора на коротких временах.
 */
const reductionOf = (
	frame: number,
	interval: Interval,
	opts: DuckingOptions,
): number => {
	if (frame < interval.from) return 0;
	// Кадр покрывает интервал времени [frame, frame+1), а громкость задаётся на
	// него одним числом. Поэтому attack считается по КОНЦУ кадра: иначе на кадре
	// начала реплики прогресс рампы равен нулю и музыка звучит неприглушённой
	// ровно там, где начинается речь. При attack 5 мс и 24 fps рампа занимает
	// 0.12 кадра — она целиком помещается внутрь первого же кадра.
	if (frame < interval.from + opts.attackFrames) {
		return opts.attackFrames === 0
			? 1
			: Math.min(1, (frame + 1 - interval.from) / opts.attackFrames);
	}
	if (frame < interval.to) return 1;
	if (frame < interval.to + opts.releaseFrames) {
		return opts.releaseFrames === 0
			? 0
			: 1 - (frame - interval.to) / opts.releaseFrames;
	}
	return 0;
};

export const musicVolumeAtFrame = (
	frame: number,
	intervals: Interval[],
	opts: DuckingOptions,
): number => {
	let reduction = 0;
	for (const interval of intervals) {
		reduction = Math.max(reduction, reductionOf(frame, interval, opts));
	}
	return (
		opts.baseVolume - reduction * (opts.baseVolume - opts.duckedVolume)
	);
};
