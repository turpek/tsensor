import pygame
import math
from loguru import logger

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
        # Tenta criar a janela. Se já existir, usa a atual.
        try:
            self.screen = pygame.display.set_mode((self.width, self.height))
        except pygame.error:
            self.screen = pygame.display.get_surface()

        pygame.display.set_caption("TSENSOR | Radar de Monitoramento")

        # Fontes
        self.font_small = pygame.font.SysFont("OCRAExtended", 20)
        self.font_large = pygame.font.SysFont("OCRAExtended", 35)

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
        angles = [30, 60, 90, 120, 150]
        line_len = self.width // 2
        for a in angles:
            rad = math.radians(a)
            end_x = self.origin_x + line_len * math.cos(math.pi - rad)
            end_y = self.origin_y - line_len * math.sin(math.pi - rad)
            pygame.draw.line(self.screen, GREEN, (self.origin_x,
                             self.origin_y), (end_x, end_y), 2)

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


if __name__ == "__main__":
    # Teste rápido manual
    radar = RadarGUI(1280, 720)
    import time
    for a in range(0, 180):
        radar.update(a, 20 if a % 10 == 0 else 50)
        time.sleep(0.05)
    radar.close()
