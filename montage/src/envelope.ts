/**
 * Огибающая громкости аудио-единицы (дизайн 2026-09-04 §2).
 *
 * Приближение и отдаление звука делаются УРОВНЕМ, а не перегенерацией: модель
 * video-to-audio синхронизирует звук с тем, что видно в кадре, и потому не
 * сыграет баркас, которого в кадре нет. План задаёт точки `[секунда, уровень]`
 * от начала единицы, здесь они превращаются в множитель на каждом кадре.
 *
 * Точки НЕ сортируются: их порядок — авторский, а непорядок ловит валидатор
 * плана (`audio_plan.py`). Молчаливая сортировка здесь означала бы, что монтаж
 * играет не то, что записано в плане.
 */

export type EnvelopePoint = [number, number];

/**
 * Уровень в момент `frameInEntry` (кадр от НАЧАЛА единицы, не эпизода).
 *
 * До первой точки держится её уровень, после последней — её же: огибающая
 * описывает изменения, а не границы звучания. Между точками — линейно.
 */
export const envelopeLevelAtFrame = (
	frameInEntry: number,
	envelope: EnvelopePoint[],
	fps: number,
): number => {
	if (envelope.length === 0) return 1;
	const seconds = frameInEntry / fps;
	const first = envelope[0];
	if (seconds <= first[0]) return first[1];
	const last = envelope[envelope.length - 1];
	if (seconds >= last[0]) return last[1];

	for (let i = 1; i < envelope.length; i++) {
		const [t1, v1] = envelope[i];
		if (seconds <= t1) {
			const [t0, v0] = envelope[i - 1];
			const span = t1 - t0;
			// Две точки в одной секунде — это скачок уровня, а не деление на ноль.
			if (span <= 0) return v1;
			return v0 + ((v1 - v0) * (seconds - t0)) / span;
		}
	}
	return last[1];
};

/**
 * Итоговая громкость единицы на кадре: базовая громкость × уровень огибающей.
 *
 * Базовая громкость остаётся балансом слоёв (речь громче музыки), огибающая —
 * движением внутри слоя. Перемножение, а не замена: иначе огибающая на одной
 * реплике сломала бы весь баланс эпизода.
 */
export const envelopeVolumeAtFrame = (
	frameInEntry: number,
	envelope: EnvelopePoint[],
	baseVolume: number,
	fps: number,
): number => baseVolume * envelopeLevelAtFrame(frameInEntry, envelope, fps);

/**
 * Громкость дорожки для Remotion: число, если уровень постоянный, и функция от
 * кадра, если задана огибающая.
 *
 * Постоянная громкость остаётся ЧИСЛОМ намеренно: функция вызывается на каждом
 * кадре рендера, и платить за это там, где уровень не меняется, незачем.
 */
export const staticTrackVolume = (
	baseVolume: number,
	envelope: EnvelopePoint[] | undefined,
	fps: number,
): number | ((frame: number) => number) =>
	envelope && envelope.length > 0
		? (frame: number) => envelopeVolumeAtFrame(frame, envelope, baseVolume, fps)
		: baseVolume;

