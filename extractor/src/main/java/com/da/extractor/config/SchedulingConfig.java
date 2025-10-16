package com.da.extractor.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * Configuración para habilitar el scheduling automático de Spring.
 *
 * Funcionalidades:
 * - Habilita la ejecución de métodos anotados con @Scheduled
 * - Permite el funcionamiento del StreamingScheduler
 * - Configura el pool de threads para tareas programadas
 */
@Configuration
@EnableScheduling
public class SchedulingConfig {
    // La configuración del pool de threads se realiza en application.properties:
    // spring.task.scheduling.pool.size=5
    // spring.task.scheduling.thread-name-prefix=etl-scheduler-
}
