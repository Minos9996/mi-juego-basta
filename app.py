import math
import random
import string
from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secreto_basta_123'
socketio = SocketIO(app)

salas = {}

# ABECEDARIO Y SISTEMA DE BOLSA GLOBAL DE LETRAS
ABECEDARIO_BASE = ['A','B','C','D','E','F','G','H','I','J','L','M','N','O','P','Q','R','S','T','U','V','Y','Z']
bolsa_letras = ABECEDARIO_BASE.copy()
random.shuffle(bolsa_letras)

def obtener_siguiente_letra():
    global bolsa_letras
    # Si la bolsa se queda sin letras, la volvemos a llenar y revolver
    if not bolsa_letras:
        bolsa_letras = ABECEDARIO_BASE.copy()
        random.shuffle(bolsa_letras)
    # Extraemos la primera letra de la bolsa
    return bolsa_letras.pop(0)

def generar_codigo():
    return ''.join(random.choices(string.ascii_uppercase, k=4))

@app.route('/')
def inicio():
    return render_template('index.html')

@socketio.on('crear_sala')
def crear_sala(datos):
    nombre = datos['nombre'].strip()
    codigo = generar_codigo() 
    
    salas[codigo] = {
        'jugadores': [nombre],
        'categorias': ["Nombre", "Apellido", "Ciudad/País", "Flor/Fruto", "Animal/Especie", "Libro/Comic/Obra de teatro", "Personaje histórico/Persona o grupo famoso", "Platillo/Postre/Bebida", "Película/Serie/Caricatura", "Canción", "Marca", "Destino turístico mexicano"],
        'host': nombre,
        'letras_usadas': [],
        'respuestas': {},
        'votos_contra': {}, 
        'puntos_manuales': {},
        'ronda_actual': 0,
        'ronda_procesada': 0,
        'basta_presionado': False,
        'rondas_totales': 3,
        'puntuaciones': {nombre: 0}
    }
    join_room(codigo) 
    emit('sala_creada', {'codigo': codigo, 'sala': salas[codigo]})

@socketio.on('unirse_sala')
def unirse_sala(datos):
    nombre = datos['nombre'].strip()
    codigo = datos['codigo'].upper().strip()
    
    if codigo in salas:
        if nombre not in salas[codigo]['jugadores']:
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
        sala['ronda_actual'] = 1 
        sala['basta_presionado'] = False
        
        # NUEVO: Obtenemos la letra de la bolsa sin repetición
        letra_elegida = obtener_siguiente_letra()
        sala['letras_usadas'].append(letra_elegida)
        
        emit('juego_iniciado', {
            'letra': letra_elegida, 
            'categorias': sala['categorias'],
            'ronda': sala['ronda_actual']
        }, to=codigo)
        
        socketio.start_background_task(temporizador_limite_ronda, codigo, sala['ronda_actual'])

def temporizador_limite_ronda(codigo, ronda):
    socketio.sleep(180) # 3 minutos
    if codigo in salas:
        sala = salas[codigo]
        if sala.get('ronda_actual') == ronda and not sala.get('basta_presionado', False):
            sala['basta_presionado'] = True
            socketio.emit('iniciar_reloj', {'quien_fue': 'El Tiempo (3 min)'}, to=codigo)

@socketio.on('basta_presionado')
def basta_presionado(datos):
    codigo = datos['codigo']
    if codigo in salas:
        salas[codigo]['basta_presionado'] = True
        emit('iniciar_reloj', {'quien_fue': datos['nombre']}, to=codigo)

@socketio.on('enviar_respuestas')
def recibir_respuestas(datos):
    codigo = datos['codigo']
    nombre = datos['nombre'].strip()
    
    if codigo in salas:
        sala = salas[codigo]
        sala['respuestas'][nombre] = datos['respuestas']
        
        if len(sala['respuestas']) == 1:
            socketio.start_background_task(esperar_rezagados, codigo, sala['ronda_actual'])
            
        if len(sala['respuestas']) == len(sala['jugadores']):
            procesar_votacion(codigo, sala['ronda_actual'])

def esperar_rezagados(codigo, ronda_actual):
    socketio.sleep(4)
    procesar_votacion(codigo, ronda_actual)

def procesar_votacion(codigo, ronda):
    if codigo not in salas: return
    sala = salas[codigo]
    
    if sala.get('ronda_procesada') == ronda: return
    sala['ronda_procesada'] = ronda
    
    for j in sala['jugadores']:
        if j not in sala['respuestas']:
            sala['respuestas'][j] = {}
            
    sala['votos_contra'] = {j: {cat: [] for cat in sala['categorias']} for j in sala['jugadores']}
    sala['puntos_manuales'] = {j: {} for j in sala['jugadores']} 
    
    respuestas_con_puntos = {}
    for j in sala['jugadores']:
        respuestas_con_puntos[j] = {}
        
    for cat in sala['categorias']:
        lista_palabras = []
        for j in sala['jugadores']:
            pal = sala['respuestas'][j].get(cat, "").strip().upper()
            if pal != "": lista_palabras.append(pal)
            
        for j in sala['jugadores']:
            palabra = sala['respuestas'][j].get(cat, "").strip().upper()
            
            if palabra == "":
                puntos = 0
            elif lista_palabras.count(palabra) == 1:
                puntos = 100
            elif lista_palabras.count(palabra) == 2:
                puntos = 50
            else:
                puntos = 25
            
            respuestas_con_puntos[j][cat] = {'texto': palabra, 'puntos_auto': puntos}
    
    socketio.emit('ir_a_votacion', {
        'respuestas': respuestas_con_puntos,
        'marcador': sala['puntuaciones'],
        'total_jugadores': len(sala['jugadores'])
    }, to=codigo)

@socketio.on('votar_contra')
def votar_contra(datos):
    codigo = datos['codigo']
    evaluado = datos['evaluado']
    categoria = datos['categoria']
    votante = datos['votante']
    
    if codigo in salas:
        sala = salas[codigo]
        lista_votos = sala['votos_contra'][evaluado][categoria]
        
        if votante in lista_votos:
            lista_votos.remove(votante)
        else:
            lista_votos.append(votante)
            
        limite = math.ceil(len(sala['jugadores']) / 2)
        
        emit('actualizar_voto', {
            'evaluado': evaluado,
            'categoria': categoria,
            'num_votos': len(lista_votos),
            'limite': limite
        }, to=codigo)

@socketio.on('forzar_puntos')
def forzar_puntos(datos):
    codigo = datos['codigo']
    evaluado = datos['evaluado']
    categoria = datos['categoria']
    nuevos_puntos = datos['puntos']
    
    if codigo in salas:
        salas[codigo]['puntos_manuales'][evaluado][categoria] = nuevos_puntos
        emit('actualizar_puntos_UI', {
            'evaluado': evaluado,
            'categoria': categoria,
            'puntos': nuevos_puntos
        }, to=codigo)

@socketio.on('cerrar_ronda_y_avanzar')
def cerrar_ronda(datos):
    codigo = datos['codigo']
    if codigo in salas:
        sala = salas[codigo]
        limite = math.ceil(len(sala['jugadores']) / 2)
        
        for cat in sala['categorias']:
            palabras_validas = []
            for j in sala['jugadores']:
                palabra = sala['respuestas'][j].get(cat, "").strip().upper()
                votos = len(sala['votos_contra'][j][cat])
                if palabra != "" and votos < limite:
                    palabras_validas.append(palabra)
                    
            for j in sala['jugadores']:
                palabra = sala['respuestas'][j].get(cat, "").strip().upper()
                votos = len(sala['votos_contra'][j][cat])
                
                if palabra == "" or votos >= limite:
                    puntos = 0
                else:
                    puntos_forzados = sala['puntos_manuales'][j].get(cat)
                    if puntos_forzados is not None:
                        puntos = puntos_forzados
                    else:
                        if palabras_validas.count(palabra) == 1:
                            puntos = 100
                        elif palabras_validas.count(palabra) == 2:
                            puntos = 50
                        else:
                            puntos = 25
                            
                sala['puntuaciones'][j] += puntos
                
        sala['respuestas'] = {}
        sala['votos_contra'] = {}
        sala['puntos_manuales'] = {}
        
        if sala['ronda_actual'] >= sala['rondas_totales']:
            emit('fin_del_juego', sala['puntuaciones'], to=codigo)
        else:
            sala['ronda_actual'] += 1
            sala['basta_presionado'] = False
            
            # NUEVO: Obtenemos la letra de la bolsa sin repetición
            letra_elegida = obtener_siguiente_letra()
            sala['letras_usadas'].append(letra_elegida)
            
            emit('juego_iniciado', {
                'letra': letra_elegida, 
                'categorias': sala['categorias'],
                'ronda': sala['ronda_actual']
            }, to=codigo)
            
            socketio.start_background_task(temporizador_limite_ronda, codigo, sala['ronda_actual'])

if __name__ == '__main__':
    socketio.run(app, debug=True)