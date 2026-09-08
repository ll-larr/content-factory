/**
 * Режим кадров: эпизод без единого отрезка.
 *
 * Кадры показываются под озвучку — это дешевле съёмки отрезков примерно в
 * десять раз и для познавательного жанра нормально, а не вынужденно.
 *
 * Python отдаёт только намерение: какие кадры и в каком порядке. Сколько кадр
 * висит на экране, решается здесь, потому что зависит от ФАКТА — длительности
 * реплики, которую измерил `parseMedia`. Две стороны, читающие одни файлы
 * разными способами, однажды разойдутся в ответе, поэтому длительностей в листе
 * нет вовсе.
 *
 * Кадр живёт столько, сколько говорит привязанная к нему реплика, плюс хвост на
 * паузу. Кадр без реплик получает минимум: молчаливая картинка тоже должна
 * успеть прочитаться.
 */
import type {MediaFacts} from './metadata';

export type ListStill = {n: number; file: string};

export type StillsSettings = {
	minSeconds: number;
	tailSeconds: number;
	crossfadeSeconds: number;
	zoom: number;
};

export type StillVoice = {
	/** Кадр, к которому привязана реплика: в этом режиме сегмент и есть кадр. */
	segment: number;
	/** Смещение внутри кадра, секунды. */
	offset: number;
	file: string;
};

export type PlacedStill = {
	n: number;
	file: string;
	from: number;
	durationInFrames: number;
};

/**
 * Сколько секунд занимает кадр: до конца последней своей реплики плюс хвост,
 * но не меньше минимума.
 */
export const stillSeconds = (
	n: number,
	voice: StillVoice[],
	media: Record<string, MediaFacts>,
	settings: StillsSettings,
): number => {
	const ends = voice
		.filter((entry) => entry.segment === n)
		.map((entry) => {
			const facts = media[entry.file];
			// Нет фактов о файле — считаем реплику нулевой длины, а не роняем
			// сборку: молчаливый кадр лучше, чем несобранный эпизод.
			const duration = facts ? facts.durationInSeconds : 0;
			return entry.offset + duration;
		});

	const spoken = ends.length ? Math.max(...ends) : 0;
	return Math.max(settings.minSeconds, spoken + settings.tailSeconds);
};

/**
 * Раскладка кадров по абсолютным кадрам таймлайна.
 *
 * Кадры идут подряд без зазора: перекрытие делает затемнение внутри самого
 * кадра, а не сдвиг соседей — иначе перекрытие съедало бы время реплики.
 */
export const placeStills = (
	stills: ListStill[],
	voice: StillVoice[],
	media: Record<string, MediaFacts>,
	settings: StillsSettings,
	fps: number,
): PlacedStill[] => {
	let from = 0;
	return stills.map((still) => {
		const seconds = stillSeconds(still.n, voice, media, settings);
		const durationInFrames = Math.max(1, Math.round(seconds * fps));
		const placed = {n: still.n, file: still.file, from, durationInFrames};
		from += durationInFrames;
		return placed;
	});
};

/**
 * Масштаб кадра в момент времени: медленный наезд от 1 до zoom.
 *
 * Наезд, а не статика: минута неподвижных картинок смотрится мёртвой. И не
 * больше нескольких процентов: заметное движение отвлекает от смысла, ради
 * которого познавательный кадр и нарисован.
 */
export const stillZoom = (
	frameInStill: number,
	durationInFrames: number,
	settings: StillsSettings,
): number => {
	if (durationInFrames <= 1) return 1;
	const progress = Math.min(1, Math.max(0, frameInStill / (durationInFrames - 1)));
	return 1 + (settings.zoom - 1) * progress;
};

/**
 * Прозрачность кадра: короткое появление и уход, чтобы смена не была рубленой.
 */
export const stillOpacity = (
	frameInStill: number,
	durationInFrames: number,
	settings: StillsSettings,
	fps: number,
): number => {
	const fade = Math.max(1, Math.round(settings.crossfadeSeconds * fps));
	if (durationInFrames <= fade * 2) return 1;
	if (frameInStill < fade) return frameInStill / fade;
	const left = durationInFrames - 1 - frameInStill;
	if (left < fade) return Math.max(0, left / fade);
	return 1;
};

/** Общая длительность эпизода в режиме кадров. */
export const stillsDuration = (placed: PlacedStill[]): number =>
	placed.reduce((total, still) => total + still.durationInFrames, 0);
