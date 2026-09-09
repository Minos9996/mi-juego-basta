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
        'categorias': ["Nombre", "Animal", "Ciudad", "Flor/Fruto", "Cosa"],
        'host': nombre,
        'letras_usadas': [],
        'respuestas': {},
        'ronda_actual': 0,
        'rondas_totales': 3,
        'puntuaciones': {nombre: 0} # Iniciamos los puntos desde cero
    }
    
    join_room(codigo) 
    emit('sala_creada', {'codigo': codigo, 'sala': salas[codigo]})

@socketio.on('unirse_sala')
def unirse_sala(datos):
    nombre = datos['nombre']
    codigo = datos['codigo'].upper()
    
    if codigo in salas:
        salas[codigo]['jugadores'].append(nombre)
        salas[codigo]['puntuaciones'][nombre] = 0 # Le damos 0 puntos al entrar
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
        
        if sala['ronda_actual'] >= sala['rondas_totales']:
            emit('fin_del_juego', sala.get('puntuaciones', {}), to=codigo)
            return
            
        sala['ronda_actual'] += 1
        
        abecedario = ['A','B','C','D','E','F','G','H','I','J','L','M','N','O','P','Q','R','S','T','U','V','Y','Z']
        disponibles = [l for l in abecedario if l not in sala['letras_usadas']]
        
        letra_elegida = random.choice(disponibles)
        sala['letras_usadas'].append(letra_elegida)
        
        emit('juego_iniciado', {
            'letra': letra_elegida, 
            'categorias': sala['categorias'],
            'ronda': sala['ronda_actual'],
            'total_rondas': sala['rondas_totales']
        }, to=codigo)

@socketio.on('basta_presionado')
def basta_presionado(datos):
    codigo = datos['codigo']
    nombre_jugador = datos['nombre']
    emit('iniciar_reloj', {'quien_fue': nombre_jugador}, to=codigo)

@socketio.on('enviar_respuestas')
def recibir_respuestas(datos):
    codigo = datos['codigo']
    nombre = datos['nombre']
    mis_palabras = datos['respuestas']
    
    if codigo in salas:
        sala = salas[codigo]
        sala['respuestas'][nombre] = mis_palabras
        
        if len(sala['respuestas']) == len(sala['jugadores']):
            respuestas_con_puntos = {}
            for j in sala['jugadores']:
                respuestas_con_puntos[j] = {}
                
            for cat in sala['categorias']:
                lista_palabras = []
                for j in sala['jugadores']:
                    palabra = sala['respuestas'][j].get(cat, "").strip().upper()
                    if palabra != "":
                        lista_palabras.append(palabra)
                        
                for j in sala['jugadores']:
                    palabra = sala['respuestas'][j].get(cat, "").strip().upper()
                    if palabra == "":
                        puntos = 0
                    elif lista_palabras.count(palabra) == 1:
                        puntos = 100
                    else:
                        puntos = 50
                        
                    sala['puntuaciones'][j] += puntos
                    if palabra == "":
                        respuestas_con_puntos[j][cat] = "*(En blanco)* (0 pts)"
                    else:
                        respuestas_con_puntos[j][cat] = f"{palabra} ({puntos} pts)"
            
            emit('ir_a_votacion', {
                'respuestas': respuestas_con_puntos,
                'marcador': sala['puntuaciones']
            }, to=codigo)
            
            sala['respuestas'] = {} 

if __name__ == '__main__':
    socketio.run(app, debug=True)