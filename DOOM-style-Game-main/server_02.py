# Necesitas instalar: pip install pygame
import socket
import threading
import pygame
import pickle

# Inicializamos pygame para obtener la resolución actual en modo pantalla completa
pygame.init()
info = pygame.display.Info()
WIDTH, HEIGHT = info.current_w, info.current_h
print(f"Resolución de pantalla completa: {WIDTH}x{HEIGHT}")

PLAYER_SIZE = 20  # Radio del círculo que representa al jugador

def create_maze(width, height):
    """
    Escala el diseño original del laberinto (basado en 800x600) a la resolución actual.
    """
    scale_x = width / 800
    scale_y = height / 600

    outer_top    = pygame.Rect(int(50 * scale_x), int(50 * scale_y), int(700 * scale_x), int(20 * scale_y))
    outer_left   = pygame.Rect(int(50 * scale_x), int(50 * scale_y), int(20 * scale_x), int(500 * scale_y))
    outer_bottom = pygame.Rect(int(50 * scale_x), int(530 * scale_y), int(700 * scale_x), int(20 * scale_y))
    outer_right  = pygame.Rect(int(730 * scale_x), int(50 * scale_y), int(20 * scale_x), int(500 * scale_y))
    
    inner_top = pygame.Rect(int(150 * scale_x), int(150 * scale_y), int(500 * scale_x), int(20 * scale_y))
    inner_left_top = pygame.Rect(int(150 * scale_x), int(150 * scale_y), int(20 * scale_x), int(120 * scale_y))
    inner_left_bottom = pygame.Rect(int(150 * scale_x), int(330 * scale_y), int(20 * scale_x), int(120 * scale_y))
    inner_bottom = pygame.Rect(int(150 * scale_x), int(430 * scale_y), int(500 * scale_x), int(20 * scale_y))
    inner_right  = pygame.Rect(int(630 * scale_x), int(150 * scale_y), int(20 * scale_x), int(300 * scale_y))
    
    maze_walls = [outer_top, outer_left, outer_bottom, outer_right,
                  inner_top, inner_left_top, inner_left_bottom, inner_bottom, inner_right]
    
    finish_area = pygame.Rect(width//2 - int(50 * scale_x), height//2 - int(50 * scale_y),
                              int(100 * scale_x), int(100 * scale_y))
    return maze_walls, finish_area

# Generamos el laberinto escalado a la resolución completa
MAZE_WALLS, FINISH_AREA = create_maze(WIDTH, HEIGHT)
COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255)]

HOST = '0.0.0.0'
PORT = 12345
FPS = 30

# ------------------ SERVIDOR ------------------
class Server:
    def __init__(self):
        self.players = {}       # Diccionario: addr -> [x, y]
        self.connections = {}   # Diccionario: addr -> socket
        self.lock = threading.Lock()
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((HOST, PORT))
        self.server.listen()
        print(f"[SERVIDOR] Escuchando en {HOST}:{PORT}")
        # Posiciones de inicio: las esquinas de la pantalla completa.
        self.spawn_positions = [
            (PLAYER_SIZE, PLAYER_SIZE),                            # Esquina superior izquierda
            (WIDTH - PLAYER_SIZE, PLAYER_SIZE),                    # Esquina superior derecha
            (PLAYER_SIZE, HEIGHT - PLAYER_SIZE),                   # Esquina inferior izquierda
            (WIDTH - PLAYER_SIZE, HEIGHT - PLAYER_SIZE)            # Esquina inferior derecha
        ]
        self.spawn_index = 0

    def broadcast_positions(self):
        """Envía a todos los clientes las posiciones actualizadas de los jugadores."""
        with self.lock:
            data = pickle.dumps(self.players)
            for conn in self.connections.values():
                try:
                    conn.sendall(data)
                except Exception as e:
                    print(f"[ERROR] Al enviar posiciones: {e}")

    def handle_client(self, conn, addr):
        """Gestiona la conexión y el movimiento de cada cliente."""
        with self.lock:
            pos = self.spawn_positions[self.spawn_index % len(self.spawn_positions)]
            self.spawn_index += 1
            self.players[addr] = list(pos)
            self.connections[addr] = conn

        self.broadcast_positions()

        try:
            while True:
                data = conn.recv(1024)
                if not data:
                    break

                direction = pickle.loads(data)
                with self.lock:
                    x, y = self.players[addr]
                    new_x, new_y = x, y
                    if direction == 'UP':
                        new_y = max(PLAYER_SIZE, y - 5)
                    elif direction == 'DOWN':
                        new_y = min(HEIGHT - PLAYER_SIZE, y + 5)
                    elif direction == 'LEFT':
                        new_x = max(PLAYER_SIZE, x - 5)
                    elif direction == 'RIGHT':
                        new_x = min(WIDTH - PLAYER_SIZE, x + 5)

                    # Aproximación del jugador con un rectángulo para detección de colisiones.
                    new_rect = pygame.Rect(new_x - PLAYER_SIZE, new_y - PLAYER_SIZE,
                                           PLAYER_SIZE * 2, PLAYER_SIZE * 2)
                    
                    collision = False
                    for wall in MAZE_WALLS:
                        if new_rect.colliderect(wall):
                            collision = True
                            break

                    if not collision:
                        self.players[addr] = [new_x, new_y]

                self.broadcast_positions()

        except Exception as e:
            print(f"[ERROR] Cliente {addr} desconectado inesperadamente: {e}")
        finally:
            with self.lock:
                print(f"[DESCONECTADO] {addr} se ha desconectado.")
                del self.players[addr]
                del self.connections[addr]
            self.broadcast_positions()
            conn.close()

    def start(self):
        """Bucle principal para aceptar nuevas conexiones."""
        print("[SERVIDOR] Esperando conexiones...")
        while True:
            try:
                conn, addr = self.server.accept()
                print(f"[NUEVA CONEXIÓN] {addr} conectado.")
                threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                print(f"[ERROR] Al aceptar conexión: {e}")

# ------------------ CLIENTE ------------------
class Client:
    def __init__(self, host):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            resolved_host = socket.gethostbyname(host)
            self.client.connect((resolved_host, PORT))
            print(f"[CLIENTE] Conectado al servidor {resolved_host}:{PORT}")
        except Exception as e:
            print(f"[ERROR] No se pudo conectar al servidor: {e}")
            exit()

        pygame.init()
        # Se crea la pantalla en modo pantalla completa.
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
        pygame.display.set_caption("Juego Multijugador - Laberinto Espiral a Pantalla Completa")
        self.clock = pygame.time.Clock()

    def send_direction(self, direction):
        """Envía la dirección seleccionada al servidor."""
        try:
            self.client.sendall(pickle.dumps(direction))
        except Exception as e:
            print(f"[ERROR] No se pudo enviar la dirección: {e}")

    def receive_positions(self):
        """Recibe la actualización de posiciones de los jugadores."""
        try:
            self.client.settimeout(0.1)
            data = self.client.recv(4096)
            return pickle.loads(data) if data else {}
        except socket.timeout:
            return {}
        except Exception as e:
            print(f"[ERROR] Al recibir posiciones: {e}")
            return {}

    def run(self):
        """Bucle principal del juego cliente."""
        running = True
        while running:
            self.clock.tick(FPS)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            keys = pygame.key.get_pressed()
            if keys[pygame.K_UP]:
                self.send_direction('UP')
            elif keys[pygame.K_DOWN]:
                self.send_direction('DOWN')
            elif keys[pygame.K_LEFT]:
                self.send_direction('LEFT')
            elif keys[pygame.K_RIGHT]:
                self.send_direction('RIGHT')

            positions = self.receive_positions()
            self.screen.fill((0, 0, 0))  # Fondo negro

            # Dibujar cada muro del laberinto (relleno gris y contorno blanco)
            for wall in MAZE_WALLS:
                pygame.draw.rect(self.screen, (100, 100, 100), wall)
                pygame.draw.rect(self.screen, (255, 255, 255), wall, 2)

            # Dibujar el área de meta en el centro (relleno dorado y contorno blanco)
            pygame.draw.rect(self.screen, (218, 165, 32), FINISH_AREA)
            pygame.draw.rect(self.screen, (255, 255, 255), FINISH_AREA, 2)

            # Dibujar a cada jugador (círculos de colores)
            for i, (addr, (x, y)) in enumerate(positions.items()):
                color = COLORS[i % len(COLORS)]
                pygame.draw.circle(self.screen, color, (x, y), PLAYER_SIZE)

            pygame.display.flip()

        pygame.quit()
        self.client.close()

# ------------------ EJECUCIÓN ------------------
if __name__ == "__main__":
    choice = input("¿Quieres iniciar como servidor (s) o cliente (c)? ").strip().lower()
    if choice == 's':
        server = Server()
        server.start()
    elif choice == 'c':
        host = input("Introduce la IP del servidor (ej: 192.168.1.10): ").strip()
        client = Client(host)
        client.run()
    else:
        print("S o c te he dicho...!. Ejecuta nuevamente e ingresa 's' para servidor o 'c' para cliente.")
