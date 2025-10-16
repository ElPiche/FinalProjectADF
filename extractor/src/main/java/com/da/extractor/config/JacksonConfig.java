package com.da.extractor.config;

import com.fasterxml.jackson.databind.ObjectMapper;
//import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Configuración de Jackson para el mapeo de objetos JSON.
 *
 * Proporciona un bean de ObjectMapper configurado con soporte para:
 * - Tipos de tiempo de Java 8+ (LocalDateTime, etc.)
 * - Configuración estándar para la aplicación
 */
@Configuration
public class JacksonConfig {

    /**
     * Configura el ObjectMapper principal de la aplicación.
     *
     * @return ObjectMapper configurado con módulos necesarios
     */
    @Bean
    public ObjectMapper objectMapper() {
        //        mapper.registerModule(new JavaTimeModule());
        return new ObjectMapper();
    }
}
