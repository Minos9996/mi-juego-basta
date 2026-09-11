import random
import string
from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secreto_basta_123'
socketio = SocketIO(app)

salas = {}

def generar_codigo():
    return ''.join(random.choices(string.ascii_uppercase, k=4))

@app.route('/')
def inicio():
    return render_template('index.html')

@socketio.on('crear_sala')
def crear_sala(datos):
    nombre = datos['nombre']
    codigo = generar_codigo() 
    
    salas[codigo] = {
        'jugadores': [nombre],
        'categorias': ["Nombre", "Apellido", "Ciudad o Pais", "Flor/Fruto", "Animal", "Destino Turistico Mexicano"],
        'host': nombre,
        'letras_usadas': [],
        'respuestas': {},
        'votos_contra': {}, # NUEVO: Memoria para los votos
        'ronda_actual': 0,
        'rondas_totales': 3,
        'puntuaciones': {nombre: 0}
    }
    join_room(codigo) 
    emit('sala_creada', {'codigo': codigo, 'sala': salas[codigo]})

@socketio.on('unirse_sala')
def unirse_sala(datos):
    nombre = datos['nombre']
    codigo = datos['codigo'].upper()
    if codigo in salas:
        salas[codigo]['jugadores'].append(nombre)
        salas[codigo]['puntuaciones'][nombre] = 0
        join_room(codigo)
        emit('ingreso_exitoso', {'codigo': codigo, 'sala': salas[codigo]})
        emit('sala_actualizada', salas[codigo], to=codigo)
    else:
        emit('error', 'Ese código de sala no existe.')

@socketio.on('agregar_categoria')
def agregar_categoria(datos):
    codigo = datos['codigo']
    nueva_categoria = datos['categoria']
    if codigo in salas:
        salas[codigo]['categorias'].append(nueva_categoria)
        emit('sala_actualizada', salas[codigo], to=codigo)

@socketio.on('iniciar_juego')
def iniciar_juego(datos):
    codigo = datos['codigo']
    if codigo in salas:
        sala = salas[codigo]
        sala['ronda_actual'] = 1 # Forzamos a que inicie la ronda 1
        
        abecedario = ['A','B','C','D','E','F','G','H','I','J','L','M','N','O','P','Q','R','S','T','U','V','Y','Z']
        disponibles = [l for l in abecedario if l not in sala['letras_usadas']]
        letra_elegida = random.choice(disponibles)
        sala['letras_usadas'].append(letra_elegida)
        
        emit('juego_iniciado', {
            'letra': letra_elegida, 
            'categorias': sala['categorias'],
            'ronda': sala['ronda_actual']
        }, to=codigo)

@socketio.on('basta_presionado')
def basta_presionado(datos):
    emit('iniciar_reloj', {'quien_fue': datos['nombre']}, to=datos['codigo'])

@socketio.on('enviar_respuestas')
def recibir_respuestas(datos):
    codigo = datos['codigo']
    nombre = datos['nombre']
    if codigo in salas:
        sala = salas[codigo]
        sala['respuestas'][nombre] = datos['respuestas']
        
        if len(sala['respuestas']) == len(sala['jugadores']):
            # Preparamos los contadores de votos para cada jugador y categoría
            sala['votos_contra'] = {j: {cat: [] for cat in sala['categorias']} for j in sala['jugadores']}
            
            emit('ir_a_votacion', {
                'respuestas': sala['respuestas'],
                'marcador': sala['puntuaciones'],
                'total_jugadores': len(sala['jugadores'])
            }, to=codigo)

# NUEVO EVENTO: Registra un voto negativo en tiempo real
@socketio.on('votar_contra')
def votar_contra(datos):
    codigo = datos['codigo']
    evaluado = datos['evaluado']
    categoria = datos['categoria']
    votante = datos['votante']
    
    if codigo in salas:
        sala = salas[codigo]
        lista_votos = sala['votos_contra'][evaluado][categoria]
        
        # Si ya había votado, quita el voto; si no, lo pone
        if votante in lista_votos:
            lista_votos.remove(votante)
        else:
            lista_votos.append(votante)
            
        limite = max(1, len(sala['jugadores']) // 2)
        
        # Avisa a todas las pantallas para actualizar los colores
        emit('actualizar_voto', {
            'evaluado': evaluado,
            'categoria': categoria,
            'num_votos': len(lista_votos),
            'limite': limite
        }, to=codigo)

# NUEVO EVENTO: El Host cierra la votación, calcula puntos y avanza
@socketio.on('cerrar_ronda_y_avanzar')
def cerrar_ronda(datos):
    codigo = datos['codigo']
    if codigo in salas:
        sala = salas[codigo]
        limite = max(1, len(sala['jugadores']) // 2)
        
        # 1. Asignar puntos considerando los votos
        for cat in sala['categorias']:
            palabras_validas = []
            # Recolectar palabras que sobrevivieron la votación
            for j in sala['jugadores']:
                palabra = sala['respuestas'][j].get(cat, "").strip().upper()
                votos = len(sala['votos_contra'][j][cat])
                if palabra != "" and votos < limite:
                    palabras_validas.append(palabra)
                    
            # Asignar el puntaje
            for j in sala['jugadores']:
                palabra = sala['respuestas'][j].get(cat, "").strip().upper()
                votos = len(sala['votos_contra'][j][cat])
                
                if palabra == "" or votos >= limite:
                    puntos = 0
                elif palabras_validas.count(palabra) == 1:
                    puntos = 100
                else:
                    puntos = 50
                    
                sala['puntuaciones'][j] += puntos
                
        # Limpiamos para la próxima ronda
        sala['respuestas'] = {}
        sala['votos_contra'] = {}
        
        # 2. Decidir si terminó el juego o vamos a la siguiente ronda
        if sala['ronda_actual'] >= sala['rondas_totales']:
            emit('fin_del_juego', sala['puntuaciones'], to=codigo)
        else:
            sala['ronda_actual'] += 1
            abecedario = ['A','B','C','D','E','F','G','H','I','J','L','M','N','O','P','Q','R','S','T','U','V','Y','Z']
            disponibles = [l for l in abecedario if l not in sala['letras_usadas']]
            letra_elegida = random.choice(disponibles)
            sala['letras_usadas'].append(letra_elegida)
            
            emit('juego_iniciado', {
                'letra': letra_elegida, 
                'categorias': sala['categorias'],
                'ronda': sala['ronda_actual']
            }, to=codigo)

if __name__ == '__main__':
    socketio.run(app, debug=True)