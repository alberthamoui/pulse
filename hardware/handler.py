"""
Handler para botão físico conectado ao GPIO.

Aguarda pressões de botão e executa callbacks.
"""

from typing import Callable, Optional


class ButtonListener:
    """Listener para eventos de botão GPIO."""
    
    def __init__(self, pin: int = 2):
        """
        Inicializa o listener de botão.
        
        Args:
            pin: Número do pino GPIO (padrão: 2)
        """
        self.pin = pin
        self.callback: Optional[Callable] = None
        self.button = None
        self.using_gpiozero = False
        
        try:
            from gpiozero import Button
            self.button = Button(pin)
            self.using_gpiozero = True
        except ImportError:
            print(f"⚠️  gpiozero não instalado. Modo simulado para pino {pin}")
    
    def iniciar(self, callback_funcao: Callable) -> None:
        """
        Inicia o listener e registra o callback.
        
        O callback é executado em thread separada quando o botão é pressionado.
        
        Args:
            callback_funcao: Função a ser chamada quando botão é pressionado
        """
        self.callback = callback_funcao
        
        if self.using_gpiozero and self.button:
            # Usa gpiozero para hardware real
            self.button.when_pressed = callback_funcao
            print(f"✅ Button listener ativo no pino GPIO {self.pin}")
        else:
            print(f"⚠️  Modo simulado para pino {self.pin}")
    
    def parar(self) -> None:
        """Para de escutar o botão."""
        if self.using_gpiozero and self.button:
            self.button.when_pressed = None
            print(f"⏹️  Button listener parado")
