package com.da.extractor;

import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

/**
 * ExtractorApplication - Aplicación principal del servicio ETL de logs.
 *
 * Este servicio extrae datos de Elasticsearch, los transforma y los carga en MongoDB.
 * Soporta dos modos de ejecución:
 *
 * 1. BATCH MODE: Ejecución única al iniciar la aplicación
 *    - Lee configuraciones de modo "batch" desde MongoDB
 *    - Ejecuta una sola vez con ventana de tiempo definida
 *    - Ideal para reportes mensuales, análisis históricos, etc.
 *
 * 2. STREAMING MODE: Ejecución continua y periódica
 *    - Lee configuraciones de modo "streaming" desde MongoDB
 *    - Ejecuta según frecuencia configurada (ej: cada 30 minutos)
 *    - Ideal para monitoreo en tiempo real, alertas, etc.
 *
 * Arquitectura:
 * - ConfigReader: Carga configuraciones al inicio
 * - BatchProcessor: Ejecuta jobs batch una sola vez
 * - StreamingScheduler: Programa jobs streaming periódicos
 * - ElasticsearchExtractor: Extrae datos de Elasticsearch
 * - DataTransformer: Transforma y agrega datos
 * - DataLoader: Carga datos en MongoDB destino
 *
 * Configuración:
 * - MongoDB Config DB: Almacena configuraciones de jobs ETL
 * - MongoDB Target DB: Destino de datos procesados
 * - Elasticsearch: Fuente de logs para extraer
 */
@Slf4j
@SpringBootApplication
public class ExtractorApplication {

	public static void main(String[] args) {
		log.info("=================================================");
		log.info("  INICIANDO SERVICIO ETL DE LOGS");
		log.info("=================================================");
		log.info("Funcionalidades:");
		log.info("• Extracción de logs desde Elasticsearch");
		log.info("• Transformación y agregación de datos");
		log.info("• Carga en MongoDB para análisis");
		log.info("• Modo Batch: Ejecución única al inicio");
		log.info("• Modo Streaming: Ejecución periódica automática");
		log.info("=================================================");

		try {
			ConfigurableApplicationContext context = SpringApplication.run(ExtractorApplication.class, args);

			log.info("=================================================");
			log.info("  SERVICIO ETL INICIADO CORRECTAMENTE");
			log.info("=================================================");
			log.info("El servicio está ejecutándose y procesando configuraciones...");
			log.info("Para detener el servicio, presione Ctrl+C");

		} catch (Exception e) {
			log.error("=================================================");
			log.error("  ERROR INICIANDO SERVICIO ETL");
			log.error("=================================================");
			log.error("Error: {}", e.getMessage(), e);
			System.exit(1);
		}
	}
}
