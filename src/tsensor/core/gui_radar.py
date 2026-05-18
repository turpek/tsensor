import pygame
import matplotlib.pyplot as plt
import numpy as np
import math
from loguru import logger
from tsensor.anicrop.spatial import Region, bbox_to_region
from tsensor.anicrop.transform import Transform, calculate_new_bbox, transform_points


# from anicrop.transform import TransformComposer, calculate_new_corners, corners_to_bbox

# Configurações de Cores
GREEN = (98, 245, 31)
DARK_GREEN = (30, 250, 60)
RED = (255, 10, 10)
BLACK = (0, 0, 0)


class RadarGUI:
    def __init__(self, width=1920, height=1080):
        if not pygame.get_init():
            pygame.init()

        self.width = width
        self.height = height
        self._window = Region.from_size(width, height)

        origin = (width // 2, height // 2)
        self._origin = Region.from_size(*origin) + origin

        # Tenta criar a janela. Se já existir, usa a atual.
        try:
            self.screen = pygame.display.set_mode((self.width, self.height))
        except pygame.error:
            self.screen = pygame.display.get_surface()

        pygame.display.set_caption("TSENSOR | Radar de Monitoramento")

        # Fallback Robusto para Fontes (especial para Python 3.14 / Arch)
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                if not pygame.font.get_init():
                    pygame.font.init()
                self.font_small = pygame.font.Font(None, 20)
                self.font_large = pygame.font.Font(None, 35)
        except (AttributeError, NotImplementedError, ImportError, pygame.error, Exception) as e:
            logger.warning(
                f"Módulo de fonte indisponível no Pygame ({e}). O radar funcionará sem textos.")

            class DummyFont:
                def render(self, *args, **kwargs):
                    return pygame.Surface((1, 1), pygame.SRCALPHA)
            self.font_small = DummyFont()
            self.font_large = DummyFont()

        # Estado do Radar
        self.angle = 0
        self.distance = 0

        # Ponto de origem do radar (centro inferior)
        self.origin_x = self.width // 2
        self.origin_y = int(self.height - self.height * 0.074)

        self.clock = pygame.time.Clock()
        logger.info("GUI Radar inicializada (Modo Manual)")

    def _draw_background(self):
        """Efeito de Motion Blur (fade gradual)."""
        blur_surf = pygame.Surface((self.width, self.height))
        blur_surf.set_alpha(25)
        blur_surf.fill(BLACK)
        self.screen.blit(blur_surf, (0, 0))

    def _draw_arcs(self):
        """Desenha os arcos de distância do radar."""
        arc_specs = [0.0625, 0.27, 0.479, 0.687]
        for spec in arc_specs:
            w = self.width - int(self.width * spec)
            h = w
            rect = pygame.Rect(self.origin_x - w // 2,
                               self.origin_y - h // 2, w, h)
            pygame.draw.arc(self.screen, GREEN, rect, 0, math.pi, 2)

    def _draw_grid_lines(self):
        """Desenha as linhas de grade (ângulos)."""

        line_len = self.width // 2
        line = Region.from_size(line_len, 1)
        rot = Transform().translate(self.origin_x, self.origin_y)

        angles = [30, 60, 90, 120, 150]
        angles_b = [-30, -60, -90, -120, -150][::-1]
        for a, ab in zip(angles, angles_b):
            rad = math.radians(a)
            end_x = self.origin_x + line_len * math.cos(math.pi - rad)
            end_y = self.origin_y - line_len * math.sin(math.pi - rad)
            mat = rot.rotate(ab, 0, 0).get_matrix(line.size)
            start, end = transform_points(
                mat, [line.top_left, line.bottom_right])
            pygame.draw.line(self.screen, GREEN, (self.origin_x,
                             self.origin_y), (end_x, end_y), 2)
            # print(f'angulo = {a} {ab}')
            # print(f'anicrop;  ({int(start[0])},{int(start[1])}), ({int(end[0])},{int(end[1])})')
            # print(f'tradic;  ({int(self.origin_x)},{int(self.origin_y)}), ({int(end_x)},{int(end_y)})\n')

        # Linha base (horizontal)
        pygame.draw.line(self.screen, GREEN, (0, self.origin_y),
                         (self.width, self.origin_y), 2)

    def _draw_sweep_line(self):
        """Desenha a linha de varredura atual."""
        rad = math.radians(self.angle)
        line_len = int(self.height - self.height * 0.12)
        end_x = self.origin_x + line_len * math.cos(math.pi - rad)
        end_y = self.origin_y - line_len * math.sin(math.pi - rad)
        pygame.draw.line(self.screen, DARK_GREEN,
                         (self.origin_x, self.origin_y), (end_x, end_y), 7)

    def _draw_detected_object(self):
        """Desenha o objeto se distance < 40."""
        if self.distance < 40 and self.distance > 0:
            rad = math.radians(self.angle)
            pix_dist = self.distance * \
                ((self.height - self.height * 0.1666) * 0.025)

            obj_x = self.origin_x + pix_dist * math.cos(math.pi - rad)
            obj_y = self.origin_y - pix_dist * math.sin(math.pi - rad)

            limit_len = self.width - int(self.width * 0.505)
            lim_x = self.origin_x + limit_len * math.cos(math.pi - rad)
            lim_y = self.origin_y - limit_len * math.sin(math.pi - rad)

            pygame.draw.line(self.screen, RED, (obj_x, obj_y),
                             (lim_x, lim_y), 9)

    def _draw_text_info(self):
        """Renderiza textos de status."""
        footer_rect = pygame.Rect(0, int(
            self.height - self.height * 0.0648), self.width, int(self.height * 0.0648))
        pygame.draw.rect(self.screen, BLACK, footer_rect)

        # Labels de distância
        labels = [("10cm", 0.3854), ("20cm", 0.281),
                  ("30cm", 0.177), ("40cm", 0.0729)]
        for text, pos in labels:
            surf = self.font_small.render(text, True, GREEN)
            self.screen.blit(
                surf, (self.width - int(self.width * pos), self.origin_y - 20))

        status = "In Range" if (
            self.distance < 40 and self.distance > 0) else "Out of Range"
        txt = f"Object: {status}  |  Angle: {self.angle}\u00b0  |  Distance: {self.distance} cm"
        surf = self.font_large.render(txt, True, GREEN)
        self.screen.blit(surf, (50, self.height - 50))

    def update(self, angle: int, distance: int):
        """
        Atualiza os dados e redesenha o frame.
        Deve ser chamada dentro do loop de aquisição.
        """
        self.angle = angle
        self.distance = distance

        # Processa eventos do Pygame para evitar que a janela trave ("Não respondendo")
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return

        self._draw_background()
        self._draw_arcs()
        self._draw_grid_lines()
        self._draw_sweep_line()
        self._draw_detected_object()
        self._draw_text_info()

        pygame.display.flip()

    def close(self):
        pygame.quit()

class EduRadarGUI:
    """
    Interface de Radar baseada no modelo Matplotlib Polar (@Edu_radar.py).
    """
    def __init__(self, distancia_max=40):
        self.distancia_max = distancia_max

        # Ativa o modo interativo do Matplotlib
        plt.ion()
        self.fig = plt.figure(facecolor='black', figsize=(8, 6))
        self.fig.canvas.manager.set_window_title('Radar ESP32 - Tempo Real')

        # Configuração do gráfico polar
        self.ax = self.fig.add_subplot(111, polar=True, facecolor='black')
        self.ax.tick_params(colors='lime')
        self.ax.grid(color='lime', alpha=0.3)
        self.ax.set_thetamin(0)
        self.ax.set_thetamax(180)
        self.ax.set_ylim(0, self.distancia_max)

        # Dados iniciais (0 a 180 graus)
        self.angulos = np.radians(np.arange(0, 181, 1))
        self.distancias = np.full(181, float(self.distancia_max))

        # Elementos gráficos
        self.linha, = self.ax.plot(self.angulos, self.distancias, color='red', linewidth=2)
        self.ponto_atual, = self.ax.plot([0], [float(self.distancia_max)], 'yo', markersize=8)

        logger.info(f"EduRadarGUI inicializado (Distância Máx: {distancia_max}cm)")

    def update(self, angle: int, distance: int):
        """
        Atualiza o radar com novo ângulo e distância.
        Simula o comportamento do loop em @Edu_radar.py.
        """
        # Verifica se a figura ainda existe
        if not plt.fignum_exists(self.fig.number):
            return

        # Lógica de saturação do modelo Edu
        if distance > self.distancia_max or distance <= 0:
            dist_val = self.distancia_max
        else:
            dist_val = distance

        # Atualiza o histórico de distâncias se o ângulo for válido
        if 0 <= angle <= 180:
            self.distancias[angle] = dist_val

            # Atualiza os dados das séries no gráfico
            self.linha.set_ydata(self.distancias)
            self.ponto_atual.set_data([np.radians(angle)], [dist_val])

            # Atualiza o desenho sem bloquear (equivalente ao plt.pause)
            try:
                self.fig.canvas.draw_idle()
                self.fig.canvas.flush_events()
            except Exception:
                pass

    def close(self):
        """Fecha a janela do radar de forma limpa."""
        try:
            plt.close(self.fig)
            plt.ioff()
            logger.info("EduRadarGUI encerrado.")
        except Exception:
            pass


if __name__ == "__main__":
    # Teste rápido manual
    radar = RadarGUI(1280, 720)
    import time
    for a in range(0, 180):
        radar.update(a, 20 if a % 10 == 0 else 50)
        time.sleep(0.05)
        if a == 2:
            break
    radar.close()
