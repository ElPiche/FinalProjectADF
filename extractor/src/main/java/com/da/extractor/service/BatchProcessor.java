package com.da.extractor.service;

import com.da.extractor.model.EtlConfiguration;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * BatchProcessor - Componente responsable de ejecutar jobs ETL en modo batch.
 *
 * Funcionalidades principales:
 * - Ejecución única de jobs al inicio de la aplicación
 * - Procesamiento de ventanas de tiempo definidas (ej: último mes)
 * - Extracción, transformación y carga secuencial
 * - Logging detallado de cada fase del proceso
 * - Manejo de errores sin afectar otros jobs
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class BatchProcessor {

    private final ElasticsearchExtractor extractor;
    private final DataTransformer transformer;
    private final DataLoader loader;

    /**
     * Ejecuta un job ETL en modo batch una sola vez.
     *
     * @param config Configuración del job ETL a ejecutar
     */
    public void executeJob(EtlConfiguration config) {
        String executionId = UUID.randomUUID().toString();
        LocalDateTime startTime = LocalDateTime.now();

        log.info("=== INICIANDO JOB BATCH: {} ===", config.getJobName());
        log.info("Execution ID: {}", executionId);
        log.info("Descripción: {}", config.getDescription());
        log.info("Índice Elasticsearch: {}", config.getElasticsearchIndex());
        log.info("Ventana de tiempo: {}", config.getTimeWindow());
        log.info("Colección destino: {}", config.getTargetCollection());

        try {
            // FASE 1: EXTRACCIÓN
            log.info("--- FASE 1: EXTRACCIÓN ---");
            List<Map<String, Object>> extractedData = extractor.extractData(
                config.getElasticsearchIndex(),
                config.getElasticsearchQuery(),
                config.getTimeWindow()
            );

            if (extractedData.isEmpty()) {
                log.warn("No se encontraron datos para extraer. Job completado sin datos.");
                return;
            }

            log.info("Extracción completada: {} registros", extractedData.size());

            // FASE 2: TRANSFORMACIÓN
            log.info("--- FASE 2: TRANSFORMACIÓN ---");
            String transformationType = determineTransformationType(config);
            List<Map<String, Object>> transformedData = transformer.transformData(extractedData, transformationType);

            log.info("Transformación completada: {} registros procesados", transformedData.size());

            // FASE 3: CARGA
            log.info("--- FASE 3: CARGA ---");
            long loadedRecords = loader.loadData(
                transformedData,
                config.getTargetCollection(),
                executionId,
                config.getJobName()
            );

            // Calcular duración total
            LocalDateTime endTime = LocalDateTime.now();
            long totalDurationMs = java.time.Duration.between(startTime, endTime).toMillis();

            log.info("=== JOB BATCH COMPLETADO EXITOSAMENTE ===");
            log.info("Job: {}", config.getJobName());
            log.info("Registros extraídos: {}", extractedData.size());
            log.info("Registros transformados: {}", transformedData.size());
            log.info("Registros cargados: {}", loadedRecords);
            log.info("Duración total: {} ms", totalDurationMs);
            log.info("========================================");

        } catch (Exception e) {
            LocalDateTime endTime = LocalDateTime.now();
            long totalDurationMs = java.time.Duration.between(startTime, endTime).toMillis();

            log.error("=== ERROR EN JOB BATCH ===");
            log.error("Job: {}", config.getJobName());
            log.error("Error: {}", e.getMessage(), e);
            log.error("Duración hasta el error: {} ms", totalDurationMs);
            log.error("==========================");

            // Re-lanzar la excepción para que sea manejada por el ConfigReader
            throw new RuntimeException("Falló la ejecución del job batch: " + config.getJobName(), e);
        }
    }

    /**
     * Determina el tipo de transformación basado en la configuración del job.
     *
     * @param config Configuración del job
     * @return Tipo de transformación a aplicar
     */
    private String determineTransformationType(EtlConfiguration config) {
        // Determinar tipo de transformación basado en el nombre del job o patrones
        String jobName = config.getJobName().toLowerCase();

        if (jobName.contains("error") || jobName.contains("exception")) {
            return "error_aggregation";
        } else if (jobName.contains("performance") || jobName.contains("response") || jobName.contains("latency")) {
            return "performance_metrics";
        } else if (jobName.contains("user") || jobName.contains("activity") || jobName.contains("usage")) {
            return "user_activity";
        } else if (jobName.contains("health") || jobName.contains("status") || jobName.contains("availability")) {
            return "system_health";
        } else {
            log.info("Usando transformación por defecto para job: {}", config.getJobName());
            return "default";
        }
    }

    /**
     * Valida que la configuración sea válida para ejecución batch.
     *
     * @param config Configuración a validar
     * @return true si es válida, false en caso contrario
     */
    public boolean isValidBatchConfiguration(EtlConfiguration config) {
        if (config == null) {
            log.warn("Configuración nula");
            return false;
        }

        if (!"batch".equalsIgnoreCase(config.getMode())) {
            log.warn("Configuración no es de modo batch: {}", config.getMode());
            return false;
        }

        if (config.getElasticsearchIndex() == null || config.getElasticsearchIndex().trim().isEmpty()) {
            log.warn("Índice de Elasticsearch no especificado para job: {}", config.getJobName());
            return false;
        }

        if (config.getTargetCollection() == null || config.getTargetCollection().trim().isEmpty()) {
            log.warn("Colección de destino no especificada para job: {}", config.getJobName());
            return false;
        }

        return true;
    }
}
