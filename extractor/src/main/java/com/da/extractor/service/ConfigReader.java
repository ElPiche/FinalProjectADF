package com.da.extractor.service;

import com.da.extractor.model.EtlConfiguration;
import com.da.extractor.repository.EtlConfigurationRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * ConfigReader - Componente responsable de leer configuraciones ETL al inicio de la aplicación.
 *
 * Funcionalidades principales:
 * - Carga automática de configuraciones desde MongoDB al arrancar la aplicación
 * - Separación entre configuraciones batch y streaming
 * - Validación de configuraciones antes de procesar
 * - Delegación a componentes especializados para cada modo
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ConfigReader {

    private final EtlConfigurationRepository configRepository;
    private final BatchProcessor batchProcessor;
    private final StreamingScheduler streamingScheduler;

    /**
     * Se ejecuta automáticamente cuando la aplicación está lista.
     * Lee todas las configuraciones activas y las procesa según su modo.
     */
    @EventListener(ApplicationReadyEvent.class)
    public void loadAndProcessConfigurations() {
        log.info("=== INICIANDO CARGA DE CONFIGURACIONES ETL ===");

        try {
            // Cargar todas las configuraciones activas
            List<EtlConfiguration> activeConfigs = configRepository.findByEnabled(true);
            log.info("Encontradas {} configuraciones activas", activeConfigs.size());

            if (activeConfigs.isEmpty()) {
                log.warn("No se encontraron configuraciones activas en MongoDB.");
                log.info("El servicio quedará en espera. Las configuraciones deben estar presentes en la base de datos.");
                return;
            }

            // Procesar configuraciones batch
            processBatchConfigurations(activeConfigs);

            // Procesar configuraciones streaming
            processStreamingConfigurations(activeConfigs);

            log.info("=== CARGA DE CONFIGURACIONES COMPLETADA ===");

        } catch (Exception e) {
            log.error("Error al cargar configuraciones ETL: {}", e.getMessage(), e);
            throw new RuntimeException("Falló la carga inicial de configuraciones", e);
        }
    }

    /**
     * Procesa las configuraciones de modo batch.
     * Ejecuta inmediatamente todos los jobs batch una sola vez.
     */
    private void processBatchConfigurations(List<EtlConfiguration> allConfigs) {
        List<EtlConfiguration> batchConfigs = allConfigs.stream()
                .filter(config -> "batch".equalsIgnoreCase(config.getMode()))
                .toList();

        log.info("Procesando {} configuraciones BATCH", batchConfigs.size());

        for (EtlConfiguration config : batchConfigs) {
            try {
                log.info("Ejecutando job batch: {} - {}", config.getJobName(), config.getDescription());
                batchProcessor.executeJob(config);
            } catch (Exception e) {
                log.error("Error ejecutando job batch {}: {}", config.getJobName(), e.getMessage(), e);
                // Continúa con el siguiente job en caso de error
            }
        }
    }

    /**
     * Procesa las configuraciones de modo streaming.
     * Registra jobs para ejecución periódica según su frecuencia.
     */
    private void processStreamingConfigurations(List<EtlConfiguration> allConfigs) {
        List<EtlConfiguration> streamingConfigs = allConfigs.stream()
                .filter(config -> "streaming".equalsIgnoreCase(config.getMode()))
                .toList();

        log.info("Registrando {} configuraciones STREAMING", streamingConfigs.size());

        for (EtlConfiguration config : streamingConfigs) {
            try {
                if (config.getFrequencyMinutes() == null || config.getFrequencyMinutes() <= 0) {
                    log.warn("Job streaming {} tiene frecuencia inválida, saltando", config.getJobName());
                    continue;
                }

                log.info("Registrando job streaming: {} - frecuencia: {} minutos",
                        config.getJobName(), config.getFrequencyMinutes());
                streamingScheduler.registerJob(config);

            } catch (Exception e) {
                log.error("Error registrando job streaming {}: {}", config.getJobName(), e.getMessage(), e);
                // Continúa con el siguiente job en caso de error
            }
        }
    }

    /**
     * Refresca las configuraciones sin reiniciar la aplicación.
     * Útil para recargar configuraciones modificadas.
     */
    public void refreshConfigurations() {
        log.info("Refrescando configuraciones ETL...");
        loadAndProcessConfigurations();
    }
}
