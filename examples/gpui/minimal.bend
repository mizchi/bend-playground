import Base
import ../../packages/bend-gpui/bend/api.bend as UI

def draw(tick: UI.Tick) -> UI.Frame:
  match tick:
    case UI.Tick{width, height, frame}:
      +red = U32.mod(U32.mul(frame, 3), 256)
      UI.pixels(width, height, U32.or(4281558528, red))

def main() -> IO(Unit):
  UI.run(640, 360, 0, tick => draw!(tick))
