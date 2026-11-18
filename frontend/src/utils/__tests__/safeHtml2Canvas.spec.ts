import { afterEach, describe, expect, it, vi } from 'vitest'
import { installZeroCanvasGuards, safeHtml2Canvas } from '@/utils/safeHtml2Canvas'

describe('safeHtml2Canvas', () => {
  const origDoc = globalThis.document
  const origCtx2D = (globalThis as any).CanvasRenderingContext2D

  afterEach(() => {
    ;(globalThis as any).document = origDoc
    ;(globalThis as any).CanvasRenderingContext2D = origCtx2D
    vi.restoreAllMocks()
  })

  it('guards createPattern and drawImage against zero-sized canvases and restores prototype', () => {
    const createPatternSpy = vi.fn().mockImplementation((img: any) => {
      if (img && (img.width === 0 || img.height === 0)) {
        throw new Error(
          "Failed to execute 'createPattern' on 'CanvasRenderingContext2D': The image argument is a canvas element with a width or height of 0.",
        )
      }
      return {} as CanvasPattern
    })
    const drawImageSpy = vi.fn().mockImplementation((img: any) => {
      if (img && (img.width === 0 || img.height === 0)) {
        throw new Error('Invalid canvas size')
      }
    })

    class FakeCtx2D {
      declare createPattern: typeof createPatternSpy
      declare drawImage: typeof drawImageSpy
    }
    FakeCtx2D.prototype.createPattern = createPatternSpy
    FakeCtx2D.prototype.drawImage = drawImageSpy
    ;(globalThis as any).CanvasRenderingContext2D = FakeCtx2D
    ;(globalThis as any).document = {
      createElement: () => ({ width: 0, height: 0 }),
    }

    const proto = FakeCtx2D.prototype as unknown as CanvasRenderingContext2D
    const zeroWidthCanvas = { width: 0, height: 20 } as HTMLCanvasElement
    const zeroHeightCanvas = { width: 20, height: 0 } as HTMLCanvasElement

    const release = installZeroCanvasGuards()
    try {
      expect(() => proto.createPattern(zeroWidthCanvas, 'no-repeat')).not.toThrow()
      expect(() => proto.createPattern(zeroHeightCanvas, 'repeat')).not.toThrow()
      expect(createPatternSpy).toHaveBeenCalledTimes(2)
      const replacement = createPatternSpy.mock.calls[0]![0]
      expect(replacement.width).toBe(1)
      expect(replacement.height).toBe(1)

      expect(() => proto.drawImage(zeroWidthCanvas, 0, 0)).not.toThrow()
      expect(() => proto.drawImage(zeroHeightCanvas, 0, 0)).not.toThrow()
      expect(drawImageSpy).not.toHaveBeenCalled()
    } finally {
      release()
      expect(FakeCtx2D.prototype.createPattern).toBe(createPatternSpy)
      expect(FakeCtx2D.prototype.drawImage).toBe(drawImageSpy)
    }
  })

  it('rejects hidden or zero-sized root elements with a readable Russian message', async () => {
    const el = {
      getBoundingClientRect: () => ({ width: 0, height: 0 }),
    } as unknown as HTMLElement

    await expect(safeHtml2Canvas(el)).rejects.toThrow('Таблица скрыта или пуста')
  })
})
